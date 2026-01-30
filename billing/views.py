from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import models
from .models import Invoice, Payment, PaymentGateway
from .forms import PaymentGatewayForm
from tenants.mixins import TenantAdminRequiredMixin
from django.views.generic import FormView
from django.urls import reverse_lazy
from booking.models import Booking
from core.models import Notification, TenantSetting
from django.urls import reverse
import json
import io
import qrcode
import base64
from fpdf import FPDF
import os
import tempfile

class PaymentSettingsView(TenantAdminRequiredMixin, FormView):
    template_name = 'billing/payment_settings.html'
    form_class = PaymentGatewayForm
    success_url = reverse_lazy('payment_settings')

    def get_initial(self):
        tenant = self.request.tenant
        initial = {}
        if tenant:
            # Load Paystack
            paystack = PaymentGateway.objects.filter(tenant=tenant, name=PaymentGateway.Provider.PAYSTACK).first()
            if paystack:
                initial['paystack_public_key'] = paystack.public_key
                initial['paystack_secret_key'] = paystack.secret_key
                initial['paystack_active'] = paystack.is_active
            
            # Load Flutterwave
            flutterwave = PaymentGateway.objects.filter(tenant=tenant, name=PaymentGateway.Provider.FLUTTERWAVE).first()
            if flutterwave:
                initial['flutterwave_public_key'] = flutterwave.public_key
                initial['flutterwave_secret_key'] = flutterwave.secret_key
                initial['flutterwave_active'] = flutterwave.is_active
        return initial

    def form_valid(self, form):
        tenant = self.request.tenant
        if not tenant:
            messages.error(self.request, "No tenant context found.")
            return redirect('dashboard')

        # Save Paystack
        PaymentGateway.objects.update_or_create(
            tenant=tenant,
            name=PaymentGateway.Provider.PAYSTACK,
            defaults={
                'public_key': form.cleaned_data['paystack_public_key'],
                'secret_key': form.cleaned_data['paystack_secret_key'],
                'is_active': form.cleaned_data['paystack_active']
            }
        )

        # Save Flutterwave
        PaymentGateway.objects.update_or_create(
            tenant=tenant,
            name=PaymentGateway.Provider.FLUTTERWAVE,
            defaults={
                'public_key': form.cleaned_data['flutterwave_public_key'],
                'secret_key': form.cleaned_data['flutterwave_secret_key'],
                'is_active': form.cleaned_data['flutterwave_active']
            }
        )

        messages.success(self.request, "Payment settings updated successfully.")
        return super().form_valid(form)

def is_admin(user):
    return user.is_authenticated and user.is_staff

@login_required
def invoice_list(request):
    # Base: Invoices for the current user (Guest View)
    invoices = Invoice.objects.filter(booking__user=request.user).order_by('-issued_date')
    
    # Financial Reports (Transactions, Monthly/Weekly Sales) - Only for Staff/Admin
    context = {'invoices': invoices}
    
    # Check if user is staff OR manager/admin via role
    is_staff_or_admin = request.user.is_staff or request.user.role in ['ADMIN', 'MANAGER']
    
    if is_staff_or_admin:
        # Transactions (All Payments)
        transactions = Payment.objects.all().order_by('-payment_date')
        
        # Calculate Date Ranges
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_week = now - timezone.timedelta(days=now.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Sales Aggregations
        monthly_sales = Payment.objects.filter(payment_date__gte=start_of_month).aggregate(total=models.Sum('amount'))['total'] or 0
        weekly_sales = Payment.objects.filter(payment_date__gte=start_of_week).aggregate(total=models.Sum('amount'))['total'] or 0
        yearly_sales = Payment.objects.filter(payment_date__gte=start_of_year).aggregate(total=models.Sum('amount'))['total'] or 0
        
        # Admin Invoice View: Show ALL invoices for the current TENANT
        all_invoices = Invoice.objects.all()
        if request.tenant:
            all_invoices = all_invoices.filter(tenant=request.tenant)
            
        # Update context
        context.update({
            'transactions': transactions,
            'monthly_sales': monthly_sales,
            'weekly_sales': weekly_sales,
            'yearly_sales': yearly_sales,
            'invoices': all_invoices.order_by('-issued_date') # Staff sees all invoices
        })
        
    return render(request, 'billing/invoice_list.html', context)

@login_required
def my_invoices(request):
    """View for guests to see their own invoices."""
    if request.user.is_staff:
        return redirect('invoice_list')
        
    invoices = Invoice.objects.filter(
        models.Q(booking__user=request.user) |
        models.Q(event_booking__user=request.user) |
        models.Q(gym_membership__user=request.user)
    ).distinct().order_by('-issued_date')
    
    return render(request, 'billing/my_invoices.html', {'invoices': invoices})

@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    
    # Determine user for permission check
    invoice_user = None
    if invoice.booking: invoice_user = invoice.booking.user
    elif invoice.event_booking: invoice_user = invoice.event_booking.user
    elif invoice.gym_membership: invoice_user = invoice.gym_membership.user
    elif invoice.orders.exists(): invoice_user = invoice.orders.first().user
    
    if not (request.user.is_staff or request.user.role in ['ADMIN', 'MANAGER']) and invoice_user != request.user:
        messages.error(request, "Access denied.")
        return redirect('home')
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})

@login_required
def make_payment(request, pk):
    """
    Redirect to payment selection using invoice ID.
    """
    invoice = get_object_or_404(Invoice, pk=pk)
    return redirect('payment_selection', invoice_id=invoice.pk)

def payment_selection(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    
    # Determine Context Object
    context_obj = None
    context_type = 'unknown'
    user = None
    email = ''
    phone = ''
    name = ''
    description = ''
    
    if invoice.orders.exists():
        order = invoice.orders.first()
        context_obj = order
        context_type = 'service'
        user = order.user
        email = user.email
        phone = getattr(user, 'phone_number', '')
        name = f"{user.first_name} {user.last_name}"
        description = f"Room Service Order #{order.order_id or order.id}"
        
        if invoice.status == Invoice.Status.PAID:
             messages.info(request, "This order is already paid.")
             return redirect('my_orders')

    elif invoice.booking:
        context_obj = invoice.booking
        context_type = 'booking'
        user = context_obj.user
        email = context_obj.guest_email
        phone = context_obj.guest_phone
        name = context_obj.guest_name
        description = f"Hotel Booking #{context_obj.booking_id}"
        
        if context_obj.status == Booking.Status.CONFIRMED and invoice.status == Invoice.Status.PAID:
             messages.info(request, "This booking is already paid and confirmed.")
             return redirect('booking_detail', pk=context_obj.pk)

    elif invoice.event_booking:
        context_obj = invoice.event_booking
        context_type = 'event'
        user = context_obj.user
        email = user.email
        phone = getattr(user, 'phone_number', '')
        name = f"{user.first_name} {user.last_name}"
        description = f"Event: {context_obj.event_name}"
        
        if context_obj.status == 'CONFIRMED' and invoice.status == Invoice.Status.PAID:
             messages.info(request, "This event is already paid and confirmed.")
             return redirect('event_booking_detail', pk=context_obj.pk)

    elif invoice.gym_membership:
        context_obj = invoice.gym_membership
        context_type = 'gym'
        user = context_obj.user
        email = user.email
        phone = getattr(user, 'phone_number', '')
        name = f"{user.first_name} {user.last_name}"
        description = f"Gym Membership: {context_obj.plan.name}"
        
        if invoice.status == Invoice.Status.PAID:
             messages.info(request, "This membership is already paid.")
             return redirect('gym_membership_list')

    elif invoice.orders.exists():
        order = invoice.orders.first()
        context_obj = order
        context_type = 'service'
        user = order.user
        email = user.email
        phone = getattr(user, 'phone_number', '')
        name = f"{user.first_name} {user.last_name}"
        description = f"Room Service Order #{order.order_id or order.id}"
        
        if invoice.status == Invoice.Status.PAID:
             messages.info(request, "This order is already paid.")
             return redirect('my_orders')

    # Security Check
    if request.user.is_authenticated:
        if not request.user.is_staff and user and user != request.user:
             messages.error(request, "Access denied.")
             return redirect('home')
    
    # Filter gateways by the invoice's tenant to ensure custom payment account
    gateways = PaymentGateway.objects.filter(is_active=True)
    if invoice.tenant:
        gateways = gateways.filter(tenant=invoice.tenant)
    elif hasattr(request, 'tenant') and request.tenant:
        gateways = gateways.filter(tenant=request.tenant)
    
    # Get Keys
    paystack_key = None
    flutterwave_key = None
    
    paystack_gw = gateways.filter(name=PaymentGateway.Provider.PAYSTACK).first()
    if paystack_gw:
        paystack_key = paystack_gw.public_key
        
    flutterwave_gw = gateways.filter(name=PaymentGateway.Provider.FLUTTERWAVE).first()
    if flutterwave_gw:
        flutterwave_key = flutterwave_gw.public_key

    context = {
        'invoice': invoice,
        'context_obj': context_obj,
        'context_type': context_type,
        'description': description,
        'paystack_enabled': paystack_gw is not None,
        'flutterwave_enabled': flutterwave_gw is not None,
        'paystack_key': paystack_key,
        'flutterwave_key': flutterwave_key,
        'amount': int(invoice.amount * 100) if paystack_gw else invoice.amount, # Paystack uses kobo
        'currency': 'NGN', # Assuming NGN for now
        'email': email,
        'phone': phone,
        'name': name,
        'ref': f"HMS-INV-{invoice.id}-{int(timezone.now().timestamp())}"
    }
    return render(request, 'billing/payment_selection.html', context)

from django.contrib.auth import get_user_model

def verify_payment(request, gateway):
    """
    Callback for payment verification
    """
    User = get_user_model()
    ref = request.GET.get('reference') or request.GET.get('tx_ref') # Paystack uses reference, FW uses tx_ref
    invoice_id = request.GET.get('invoice_id')
    
    if not ref or not invoice_id:
        messages.error(request, "Invalid payment verification parameters.")
        return redirect('home')
        
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    
    # In a real app, verify with backend API using secret key
    success = True # Simulate verification
    
    if success:
        if invoice.status != Invoice.Status.PAID:
            # Create Payment Record
            Payment.objects.create(
                invoice=invoice,
                amount=invoice.amount,
                payment_method=gateway.upper(),
                transaction_id=ref
            )
            
            # Update Invoice
            invoice.status = Invoice.Status.PAID
            invoice.save()
            
            # Handle Specific Object Updates & Notifications
            redirect_url = 'home'
            
            if invoice.orders.exists():
                # Orders handle their own status based on payment if needed
                # Usually we move from AWAITING_PAYMENT to PENDING (for kitchen)
                for order in invoice.orders.all():
                    if order.status == 'AWAITING_PAYMENT':
                        order.status = 'PENDING'
                        order.save()
                        
                        # Notify Kitchen/Staff
                        has_food = order.items.filter(menu_item__category='FOOD').exists()
                        has_drink = order.items.filter(menu_item__category='DRINK').exists()
                        
                        roles_to_notify = [User.Role.ADMIN, User.Role.MANAGER]
                        if has_food:
                            roles_to_notify.append(User.Role.KITCHEN)
                        if has_drink:
                            roles_to_notify.append(User.Role.BAR)
                            
                        # Find users with these roles in the current tenant
                        tenant_users = User.objects.filter(
                            memberships__tenant=invoice.tenant,
                            role__in=roles_to_notify
                        ).distinct()
                        
                        for staff in tenant_users:
                            # Only notify if role matches the content (e.g. Kitchen doesn't need to know about Drink-only)
                            # But Admin/Manager always gets it.
                            should_notify = False
                            if staff.role in [User.Role.ADMIN, User.Role.MANAGER]:
                                should_notify = True
                            elif staff.role == User.Role.KITCHEN and has_food:
                                should_notify = True
                            elif staff.role == User.Role.BAR and has_drink:
                                should_notify = True
                                
                            if should_notify:
                                Notification.objects.create(
                                    recipient=staff,
                                    title="New Order Received",
                                    message=f"Order #{order.order_id or order.id} ({'Food' if has_food else ''}{' & ' if has_food and has_drink else ''}{'Drink' if has_drink else ''}) needs attention.",
                                    link=reverse('staff_order_list')
                                )
                        
                redirect_url = 'my_orders'
                redirect_pk = None

            elif invoice.booking:
                booking = invoice.booking
                # Only update status if not already checked in/completed
                if booking.status not in [Booking.Status.CHECKED_IN, Booking.Status.CHECKED_OUT, Booking.Status.CANCELLED]:
                    booking.status = Booking.Status.CONFIRMED
                    booking.save()
                
                # Check if Staff or Public
                if request.user.is_staff:
                    redirect_url = 'booking_detail'
                    redirect_pk = booking.pk
                else:
                    # Public Success Page
                    return render(request, 'booking/booking_success.html', {
                        'booking': booking, 
                        'site_settings': TenantSetting.objects.filter(tenant=invoice.tenant).first()
                    })
                
            elif invoice.event_booking:
                booking = invoice.event_booking
                booking.status = 'CONFIRMED'
                booking.save()
                redirect_url = 'event_booking_detail'
                redirect_pk = booking.pk
                
            elif invoice.gym_membership:
                membership = invoice.gym_membership
                membership.status = 'ACTIVE'
                membership.save()
                redirect_url = 'gym_membership_list'
                redirect_pk = None
            
            messages.success(request, "Payment successful!")
            if redirect_pk:
                return redirect(redirect_url, pk=redirect_pk)
            return redirect(redirect_url)
            
    messages.error(request, "Payment verification failed.")
    return redirect('home')

@login_required
def download_receipt(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    
    # Permission check: Owner or Staff
    invoice_user = None
    if invoice.booking: invoice_user = invoice.booking.user
    elif invoice.event_booking: invoice_user = invoice.event_booking.user
    elif invoice.gym_membership: invoice_user = invoice.gym_membership.user
    elif invoice.orders.exists(): invoice_user = invoice.orders.first().user

    if not request.user.is_staff and invoice_user != request.user:
         messages.error(request, "You do not have permission to download this receipt.")
         return redirect('home')

    tenant = invoice.tenant
    settings = None
    if tenant:
        settings = TenantSetting.objects.filter(tenant=tenant).first()
    
    # Fallback values if no settings found
    current_theme = settings.theme if settings else 'theme-default'
    currency_symbol = settings.currency if settings else 'NGN' # Using currency code as symbol for now or mapping it
    hotel_name = settings.hotel_name if settings else "Hotel Management System"
    
    # Simple currency mapping
    CURRENCY_SYMBOLS = {
        'USD': '$', 'EUR': '€', 'GBP': '£', 'NGN': '₦', 
        'JPY': '¥', 'CAD': '$', 'AUD': '$', 'INR': '₹', 'ZAR': 'R'
    }
    if settings:
        currency_symbol = CURRENCY_SYMBOLS.get(settings.currency, settings.currency)

    # Define Theme Colors (R, G, B)
    THEME_COLORS = {
        'theme-default': (19, 236, 109),
        'theme-light': (19, 236, 109), 
        'theme-blue': (59, 130, 246), 
        'theme-luxury': (212, 175, 55),
        'theme-forest': (74, 222, 128),
        'theme-ocean': (6, 182, 212),
        'theme-sunset': (244, 114, 182),
        'theme-royal': (167, 139, 250),
        'theme-minimal': (113, 113, 122),
    }

    primary_color = THEME_COLORS.get(current_theme, (19, 236, 109))
    
    # Generate PDF (Standard Receipt Size - A5)
    pdf = FPDF(orientation='P', unit='mm', format='A5')
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    # --- Decorative Header ---
    pdf.set_y(10)
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(*primary_color)
    pdf.cell(0, 8, txt=hotel_name.upper(), ln=1, align="R")
    
    pdf.set_font("Arial", '', 8)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 4, txt="Official Receipt", ln=1, align="R")
    
    pdf.ln(2)
    pdf.set_draw_color(*primary_color)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 138, pdf.get_y())
    pdf.set_line_width(0.2)

    # --- Receipt Info ---
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(70, 10, txt="RECEIPT", ln=0, align="L")
    
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(58, 10, txt=f"INV #{invoice.id}", ln=1, align="R", fill=True)
    
    pdf.ln(5)
    
    # --- Details ---
    col_y = pdf.get_y()
    
    # Bill To
    pdf.set_fill_color(*primary_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(60, 6, txt="  BILL TO", ln=1, fill=True)
    
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Arial", 'B', 10)
    pdf.ln(2)
    
    guest_name = "Guest"
    guest_email = ""
    
    if invoice.orders.exists():
        order = invoice.orders.first()
        guest_name = f"{order.user.first_name} {order.user.last_name}"
        guest_email = order.user.email
    elif invoice.booking:
        guest_name = invoice.booking.guest_name
        guest_email = invoice.booking.guest_email
    elif invoice_user:
        guest_name = f"{invoice_user.first_name} {invoice_user.last_name}"
        guest_email = invoice_user.email
        
    pdf.cell(60, 5, txt=guest_name, ln=1)
    pdf.set_font("Arial", '', 9)
    pdf.cell(60, 4, txt=guest_email, ln=1)
    
    # Details Column
    pdf.set_xy(80, col_y)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(58, 6, txt="  DETAILS", ln=1, fill=True)
    
    pdf.set_x(80)
    pdf.ln(2)
    
    def print_detail_row(label, value):
        x = pdf.get_x()
        pdf.set_font("Arial", '', 8)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(20, 4, txt=label, align="L")
        pdf.set_font("Arial", 'B', 8)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(38, 4, txt=value, align="R", ln=1)
        pdf.set_x(x)

    pdf.set_x(80)
    print_detail_row("Date:", invoice.issued_date.strftime("%Y-%m-%d"))
    
    status = invoice.get_status_display().upper()
    print_detail_row("Status:", status)
    
    payment = invoice.payments.last()
    if payment:
        print_detail_row("Method:", payment.get_payment_method_display())
        print_detail_row("Ref:", payment.transaction_id[:15] + "..." if len(payment.transaction_id) > 15 else payment.transaction_id)

    pdf.ln(10)
    
    # --- Line Items ---
    pdf.set_y(max(pdf.get_y(), col_y + 35))
    
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Arial", 'B', 9)
    
    w_desc = 98
    w_total = 30
    
    pdf.cell(w_desc, 8, txt="  Description", border="B", fill=True)
    pdf.cell(w_total, 8, txt="Total  ", border="B", fill=True, align="R", ln=1)
    
    pdf.set_font("Arial", '', 9)
    
    desc = "Service Charge"
    if invoice.orders.exists():
        desc = f"Room Service Order #{invoice.orders.first().order_id or invoice.orders.first().id}"
    elif invoice.booking:
        desc = f"Hotel Booking: {invoice.booking.room.room_type.name}"
    elif invoice.event_booking:
        desc = f"Event Booking: {invoice.event_booking.event_name}"
    elif invoice.gym_membership:
        desc = f"Gym Membership: {invoice.gym_membership.plan.name}"
        
    pdf.cell(w_desc, 8, txt=f"  {desc}", border="B")
    pdf.cell(w_total, 8, txt=f"{currency_symbol}{invoice.amount}  ", border="B", align="R", ln=1)
    
    # Totals
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(w_desc, 8, txt="TOTAL", align="R")
    pdf.cell(w_total, 8, txt=f"{currency_symbol}{invoice.amount}  ", align="R", border="T")
    
    # Output
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
        tmp_pdf_path = tmp_pdf.name

    try:
        pdf.output(name=tmp_pdf_path, dest='F')
        with open(tmp_pdf_path, 'rb') as f:
            pdf_content = f.read()
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Receipt_{invoice.id}.pdf"'
    finally:
        if os.path.exists(tmp_pdf_path):
            os.unlink(tmp_pdf_path)
            
    return response

@user_passes_test(is_admin)
def payment_settings(request):
    gateways = PaymentGateway.objects.all()
    
    # Ensure default entries exist
    if not gateways.exists():
        PaymentGateway.objects.get_or_create(name=PaymentGateway.Provider.PAYSTACK)
        PaymentGateway.objects.get_or_create(name=PaymentGateway.Provider.FLUTTERWAVE)
        gateways = PaymentGateway.objects.all()
    
    if request.method == 'POST':
        for gw in gateways:
            is_active = request.POST.get(f"{gw.name}_active") == 'on'
            public_key = request.POST.get(f"{gw.name}_public")
            secret_key = request.POST.get(f"{gw.name}_secret")
            
            gw.is_active = is_active
            gw.public_key = public_key
            gw.secret_key = secret_key
            gw.save()
        
        messages.success(request, "Payment settings updated.")
        return redirect('payment_settings')
        
    return render(request, 'billing/payment_settings.html', {'gateways': gateways})