from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import UpdateView
from django.urls import reverse_lazy
from django.contrib import messages
from .forms import TenantForm, TenantSettingsForm
from .models import Tenant, Domain, Membership, Plan
from .mixins import TenantAdminRequiredMixin
from django.utils import timezone
from datetime import timedelta

class TenantSettingsView(TenantAdminRequiredMixin, UpdateView):
    model = Tenant
    form_class = TenantSettingsForm
    template_name = 'tenants/settings.html'
    success_url = reverse_lazy('tenant_settings')

    def get_object(self, queryset=None):
        return self.request.tenant
    
    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill custom domain
        primary_domain = self.object.domains.filter(is_primary=True).first()
        if primary_domain:
            initial['custom_domain'] = primary_domain.domain
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Calculate Platform Domain
        host = self.request.get_host()
        platform_domain = host
        if self.object.subdomain and host.startswith(f"{self.object.subdomain}."):
            platform_domain = host[len(self.object.subdomain)+1:]
            
        context['platform_domain'] = platform_domain
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Handle Custom Domain Update
        custom_domain = form.cleaned_data.get('custom_domain')
        tenant = self.object
        
        # Check if plan allows it (only if they are trying to set one)
        if custom_domain and not tenant.plan.allow_custom_domain:
             messages.error(self.request, "Upgrade to Premium to use a custom domain.")
             return redirect('tenant_settings')

        if custom_domain:
            # Check if domain exists (and not owned by this tenant)
            if Domain.objects.filter(domain=custom_domain).exclude(tenant=tenant).exists():
                messages.error(self.request, "This domain is already in use by another workspace.")
                return redirect('tenant_settings')

            # Update or Create Domain
            domain_obj = tenant.domains.filter(is_primary=True).first()
            if domain_obj:
                if domain_obj.domain != custom_domain:
                    domain_obj.domain = custom_domain
                    domain_obj.save()
                    messages.success(self.request, f"Custom domain updated to {custom_domain}")
            else:
                Domain.objects.create(tenant=tenant, domain=custom_domain, is_primary=True)
                messages.success(self.request, f"Custom domain linked: {custom_domain}")
        else:
            # If empty, check if we need to remove existing one
            domain_obj = tenant.domains.filter(is_primary=True).first()
            if domain_obj:
                domain_obj.delete()
                messages.info(self.request, "Custom domain removed.")
            
        messages.success(self.request, "Hotel settings updated successfully.")
        return response

from django.utils.text import slugify

from core.email_utils import send_branded_email

@login_required
def create_tenant(request):
    plan_name = request.GET.get('plan') or request.POST.get('plan')
    plan = None
    
    if plan_name:
        plan = Plan.objects.filter(name__iexact=plan_name).first()
    
    # Enforce Plan Selection
    if not plan:
        messages.warning(request, "Please select a subscription plan to continue.")
        return redirect('/#pricing') # Redirect to landing page pricing section

    if request.method == 'POST':
        form = TenantForm(request.POST)
        if form.is_valid():
            tenant = form.save(commit=False)
            tenant.owner = request.user
            tenant.plan = plan
            
            # --- Domain & Subdomain Logic ---
            hotel_name = form.cleaned_data['name']
            custom_domain = form.cleaned_data.get('domain')
            
            # 1. Determine Subdomain (Always use Hotel Name)
            tenant.slug = slugify(hotel_name)
            tenant.subdomain = slugify(hotel_name)
            
            # Check for subdomain collision
            if Tenant.objects.filter(subdomain=tenant.subdomain).exists():
                 messages.error(request, f"The name '{hotel_name}' generates a subdomain that is already taken. Please choose a different hotel name.")
                 return render(request, 'tenants/create_tenant.html', {'form': form, 'plan': plan})

            # 2. Handle Custom Domain
            primary_domain_str = f"{tenant.subdomain}.localhost" # Default fallback
            
            if custom_domain:
                if not plan.allow_custom_domain:
                     messages.error(request, "Custom domains are only available on the Premium plan.")
                     return render(request, 'tenants/create_tenant.html', {'form': form, 'plan': plan})
                primary_domain_str = custom_domain
            else:
                # Default domain construction (e.g., hotel-slug.saas.com or localhost)
                # In dev, usually subdomain.localhost:8000
                pass
                
            # Calculate Price based on Billing Cycle
            price = plan.price
            if tenant.billing_cycle == 'yearly':
                price = plan.price * 12 # Simple multiplication, can add discount logic later
            
            # If paid plan, set as inactive initially
            if price > 0:
                tenant.is_active = False
                tenant.subscription_status = 'pending_payment'
            else:
                tenant.is_active = True
                tenant.subscription_status = 'active'
                tenant.subscription_end_date = timezone.now() + timedelta(days=365*10) # Free forever essentially
            
            tenant.save()
            
            # Create Domain(s)
            # Always create the subdomain version
            # Dynamically determine the root domain from request to avoid hardcoding "localhost"
            current_host = request.get_host()
            base_host = current_host.split(':')[0] # Remove port
            
            if 'localhost' in base_host:
                root_domain = 'localhost'
            else:
                # Assuming current host is the SaaS domain
                root_domain = base_host
                
            default_domain = f"{tenant.subdomain}.{root_domain}"
            
            Domain.objects.create(
                tenant=tenant,
                domain=default_domain,
                is_primary=not custom_domain # Primary if no custom domain
            )
            
            if custom_domain:
                Domain.objects.create(
                    tenant=tenant,
                    domain=custom_domain,
                    is_primary=True
                )
            
            # Create Membership
            Membership.objects.create(
                user=request.user,
                tenant=tenant,
                role='ADMIN'
            )
            
            # Redirect logic
            if plan and plan.price > 0:
                messages.info(request, "Please complete payment to activate your subscription.")
                return redirect('tenant_payment', tenant_id=tenant.id)
            
            # Redirect to new tenant dashboard
            protocol = 'https' if request.is_secure() else 'http'
            
            # Construct domain dynamically based on current host
            current_host = request.get_host()
            base_host = current_host.split(':')[0]
            
            if 'localhost' in base_host:
                root_domain = 'localhost'
            else:
                root_domain = base_host

            target_domain = custom_domain if custom_domain else f"{tenant.subdomain}.{root_domain}"
            
            # Add port back if it was on localhost/dev and NOT a custom domain (unless custom domain needs port?)
            # Usually custom domains point to standard 80/443, but in dev we might need port.
            # If target is subdomain.localhost, we append port.
            if 'localhost' in target_domain and ':' in current_host and ':' not in target_domain:
                port = current_host.split(':')[1]
                target_domain = f"{target_domain}:{port}"
            
            dashboard_url = f"{protocol}://{target_domain}/dashboard/"
            
            # Send Welcome Email (Only if active/free)
            if tenant.is_active:
                try:
                    send_branded_email(
                        subject=f"Welcome to Spaxce - {tenant.name} Created",
                        template_name='emails/welcome_hotel.html',
                        context={
                            'user': request.user,
                            'tenant': tenant,
                            'dashboard_url': dashboard_url,
                        },
                        recipient_list=[request.user.email],
                        tenant=None # Sent from Platform
                    )
                except Exception as e:
                    print(f"Failed to send welcome email: {e}")

            return redirect(dashboard_url)
    else:
        form = TenantForm()
    
    return render(request, 'tenants/create_tenant.html', {'form': form, 'plan': plan})

@login_required
def tenant_payment(request, tenant_id):
    tenant = get_object_or_404(Tenant, id=tenant_id, owner=request.user)
    
    # Check for Upgrade Flow
    upgrade_plan_id = request.session.get('upgrade_plan_id')
    upgrade_plan = None
    if upgrade_plan_id:
        upgrade_plan = Plan.objects.filter(id=upgrade_plan_id).first()
    
    # Only block if NOT upgrading
    if not upgrade_plan and tenant.is_active and tenant.subscription_status == 'active':
        messages.info(request, "This workspace is already active.")
        return redirect('home') # Or dashboard if we could construct url
    
    plan_to_pay = upgrade_plan if upgrade_plan else tenant.plan
    amount = plan_to_pay.price
    if tenant.billing_cycle == 'yearly':
        amount = plan_to_pay.price * 12
        
    # Fetch Public Keys for Template
    from billing.models import PaymentGateway
    paystack_key = None
    flutterwave_key = None
    
    # Use 'PAYSTACK' (uppercase) as it's the choice value
    paystack_gateway = PaymentGateway.objects.filter(tenant=None, name='PAYSTACK', is_active=True).first()
    if paystack_gateway:
        paystack_key = paystack_gateway.public_key
        
    flutterwave_gateway = PaymentGateway.objects.filter(tenant=None, name='FLUTTERWAVE', is_active=True).first()
    if flutterwave_gateway:
        flutterwave_key = flutterwave_gateway.public_key
        
    return render(request, 'tenants/payment.html', {
        'tenant': tenant, 
        'plan': plan_to_pay, 
        'amount': amount,
        'paystack_key': paystack_key,
        'flutterwave_key': flutterwave_key,
        'is_upgrade': bool(upgrade_plan)
    })

from core.models import AuditLog
from core.utils import log_audit

@login_required
def process_payment(request, tenant_id):
    if request.method != 'POST':
        return redirect('tenant_payment', tenant_id=tenant_id)
        
    tenant = get_object_or_404(Tenant, id=tenant_id, owner=request.user)
    
    # Get Gateway (Paystack or Flutterwave)
    # For SaaS platform, we use platform-level gateways (tenant=None)
    gateway_name = request.POST.get('gateway', 'PAYSTACK') # Default to Paystack
    
    # In a real scenario, we would verify the transaction reference here
    reference = request.POST.get('reference')
    
    # Mock Verification Logic
    success = False
    if reference:
        # Verify with API based on gateway
        # NOTE: For SaaS platform, we use platform-level gateways.
        # We need to fetch the platform gateway credentials (tenant=None)
        
        from billing.models import PaymentGateway
        import requests
        
        try:
            if gateway_name == 'PAYSTACK':
                gateway = PaymentGateway.objects.filter(tenant=None, name='PAYSTACK', is_active=True).first()
                if gateway and gateway.secret_key:
                    headers = {'Authorization': f'Bearer {gateway.secret_key}'}
                    response = requests.get(f'https://api.paystack.co/transaction/verify/{reference}', headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        if data['status'] and data['data']['status'] == 'success':
                            success = True
                            
            elif gateway_name == 'FLUTTERWAVE':
                gateway = PaymentGateway.objects.filter(tenant=None, name='FLUTTERWAVE', is_active=True).first()
                if gateway and gateway.secret_key:
                    headers = {'Authorization': f'Bearer {gateway.secret_key}'}
                    response = requests.get(f'https://api.flutterwave.com/v3/transactions/{reference}/verify', headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        if data['status'] == 'success':
                            success = True
        except Exception as e:
            print(f"Payment Verification Error: {e}")
            # Fallback to False if verification fails/errors out
            success = False
            
        # success = True # REMOVE THIS IN PRODUCTION - Only for dev if APIs fail
        # For now, if no gateway is configured, we might want to allow dev bypass?
        pass 
    
    if not success:
        # Fallback for manual button click in dev (only if no reference passed)
        # In production, frontend should always pass reference
        # But wait, if user clicks 'Pay Securely' in the mock template, it sends a mock reference 'REF-...' 
        # And since we don't have a real Paystack/Flutterwave transaction with that ID, the API check above fails (success=False)
        # So we fall into the failure block.
        
        # FIX: Check if we are in DEBUG mode or if keys are missing to allow mock reference
        from django.conf import settings
        if settings.DEBUG:
            # Check if it looks like our mock reference
            mock_ref = request.POST.get('reference', '')
            if mock_ref.startswith('REF-'):
                success = True
    
    if success:
        # Check for Upgrade
        upgrade_plan_id = request.session.get('upgrade_plan_id')
        is_upgrade = False
        if upgrade_plan_id:
            upgrade_plan = Plan.objects.filter(id=upgrade_plan_id).first()
            if upgrade_plan:
                tenant.plan = upgrade_plan
                is_upgrade = True
                del request.session['upgrade_plan_id']

        tenant.is_active = True
        tenant.subscription_status = 'active'
        
        # Save Auto-Renew Preference & Auth Code
        # In a real integration, the 'data' from verification response contains 'authorization' object
        # with 'authorization_code' for recurring billing.
        # We will mock it here or try to extract if 'data' variable was available in scope (it was inside try block)
        
        # Assuming we want auto-renew enabled by default on payment
        tenant.auto_renew = True 
        
        # Mock Auth Code for testing auto-renewal
        if not tenant.payment_auth_code:
            tenant.payment_auth_code = f"AUTH-{reference}"
        
        # Update subscription end date based on billing cycle
        days = 365 if tenant.billing_cycle == 'yearly' else 30
        tenant.subscription_end_date = timezone.now() + timedelta(days=days)
        tenant.save()
        
        # Create Invoice and Payment Record
        from billing.models import Invoice, Payment
        import uuid
        
        amount = tenant.plan.price if tenant.plan else 0
        
        invoice = Invoice.objects.create(
            tenant=tenant,
            amount=amount,
            status=Invoice.Status.PAID,
            invoice_type=Invoice.Type.SUBSCRIPTION,
            due_date=timezone.now().date()
        )
        
        Payment.objects.create(
            invoice=invoice,
            amount=amount,
            payment_method=gateway_name,
            transaction_id=reference or f"REF-{uuid.uuid4().hex[:10]}",
            payment_date=timezone.now()
        )
        
        # Log Audit
        log_audit(
            request,
            action=AuditLog.Action.PAYMENT,
            module='Subscription',
            details=f"Processed subscription payment for {tenant.name}. Plan: {tenant.plan.name if tenant.plan else 'None'}. Upgrade: {is_upgrade}"
        )
        
        # Redirect to Dashboard Logicnew tenant dashboard
        protocol = 'https' if request.is_secure() else 'http'
        # Get primary domain
        domain_obj = tenant.domains.filter(is_primary=True).first()
        # Fallback to subdomain logic if no domain object (which is common in dev)
        
        # Logic from register_view to construct correct URL
        current_host = request.get_host()
        base_host = current_host.split(':')[0]
        if 'localhost' in base_host:
            root_domain = 'localhost'
        else:
            root_domain = base_host
            
        target_domain = f"{tenant.subdomain}.{root_domain}"
        
        if 'localhost' in target_domain and ':' in current_host and ':' not in target_domain:
             port = current_host.split(':')[1]
             target_domain = f"{target_domain}:{port}"
             
        dashboard_url = f"{protocol}://{target_domain}/dashboard/"
        
        if is_upgrade:
            messages.success(request, f"Upgrade to {tenant.plan.name} successful!")
        else:
            messages.success(request, f"Payment successful! Welcome to {tenant.name}.")
            # Send Welcome Email only for new activations
            try:
                send_branded_email(
                    subject=f"Welcome to Spaxce - {tenant.name} Active",
                    template_name='emails/welcome_hotel.html',
                    context={
                        'user': request.user,
                        'tenant': tenant,
                        'dashboard_url': dashboard_url,
                    },
                    recipient_list=[request.user.email],
                    tenant=None # Sent from Platform
                )
            except Exception as e:
                print(f"Failed to send welcome email: {e}")
            
        return redirect(dashboard_url)
    else:
        messages.error(request, "Payment failed. Please try again.")
        return redirect('tenant_payment', tenant_id=tenant_id)

@login_required
def upgrade_subscription(request, plan_id):
    """Initiates the upgrade process"""
    plan = get_object_or_404(Plan, id=plan_id)
    
    # Ensure tenant exists for this user (owner)
    tenant = Tenant.objects.filter(owner=request.user).first()
    
    if not tenant:
        messages.error(request, "No workspace found to upgrade.")
        return redirect('home')
        
    if tenant.owner != request.user:
         messages.error(request, "Only the owner can upgrade the subscription.")
         return redirect('home')

    # Set session variable for upgrade
    request.session['upgrade_plan_id'] = plan.id
    
    return redirect('tenant_payment', tenant_id=tenant.id)

@login_required
def enable_auto_renew(request):
    if request.method == 'POST' and request.tenant:
        # Check permissions
        if request.tenant.owner != request.user:
             messages.error(request, "Permission denied.")
             return redirect('tenant_settings')
             
        # Toggle based on POST data or simple toggle?
        # Usually a toggle switch sends 'on' or nothing.
        # Let's assume this view enables it. For disable, we might use cancel_subscription or a separate toggle.
        # But 'enable_auto_renew' implies enabling.
        
        enable = request.POST.get('auto_renew') == 'on'
        request.tenant.auto_renew = enable
        request.tenant.save()
        
        status = "enabled" if enable else "disabled"
        messages.success(request, f"Automatic renewal has been {status}.")
        return redirect('tenant_settings')
    return redirect('tenant_settings')

@login_required
def cancel_subscription(request):
    if request.method == 'POST' and request.tenant:
        if request.tenant.owner != request.user:
             messages.error(request, "Permission denied.")
             return redirect('tenant_settings')
             
        # Cancel auto-renew instead of immediate cancellation?
        # "Make sure... they can also disable it if they dont want that"
        request.tenant.auto_renew = False
        request.tenant.save()
        messages.success(request, "Automatic renewal disabled. Your subscription will remain active until the end of the billing period.")
        return redirect('tenant_settings')
    return redirect('tenant_settings')