from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.db import transaction
from django.db.models import Sum, Count
from django.utils.text import slugify
from django.contrib import messages
from tenants.mixins import TenantAdminRequiredMixin
from .forms import RegistrationForm, LoginForm, UserForm, HotelSignupForm
from .models import User
from booking.models import Booking
from billing.models import Invoice
from hotel.models import Room
from services.models import GuestOrder
from events.models import EventBooking
from gym.models import GymMembership
from tenants.models import Tenant, Domain, Plan, Membership
from django.utils import timezone
from datetime import timedelta
from core.email_utils import send_branded_email

def login_view(request):
    # Check if we are on a tenant subdomain
    # If so, restrict login to members of this tenant only
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            
            # Subdomain Login Restriction
            if request.tenant and request.tenant.subdomain != 'public':
                # Check if user is a member or the owner
                # Superusers can access anywhere
                if not user.is_superuser:
                    from tenants.models import Membership
                    is_member = Membership.objects.filter(user=user, tenant=request.tenant).exists()
                    is_owner = (request.tenant.owner == user)
                    
                    if not is_member and not is_owner:
                        messages.error(request, "Access Denied: You are not a member of this workspace.")
                        return render(request, 'accounts/login.html', {'form': form})
            
            login(request, user)
            
            # Check if user is a tenant owner and redirect to their subdomain
            # This is critical for SaaS multi-tenancy flow
            # If we are on the main platform domain (tenant is None or public)
            # and the user owns a tenant, send them there.
            
            if not request.tenant or request.tenant.subdomain == 'public':
                # Superuser Redirect (Platform Dashboard)
                if user.is_superuser:
                    return redirect('platform_dashboard')

                # Check for owned tenants
                owned_tenant = user.owned_tenants.first()
                if owned_tenant:
                    # Construct Redirect URL
                    protocol = 'https' if request.is_secure() else 'http'
                    current_host = request.get_host()
                    base_host = current_host.split(':')[0]
                    
                    if 'localhost' in base_host:
                        root_domain = 'localhost'
                    else:
                        root_domain = base_host
                        
                    target_domain = f"{owned_tenant.subdomain}.{root_domain}"
                    
                    if 'localhost' in target_domain and ':' in current_host and ':' not in target_domain:
                         port = current_host.split(':')[1]
                         target_domain = f"{target_domain}:{port}"
                         
                    return redirect(f"{protocol}://{target_domain}/dashboard/")
            
            return redirect('dashboard')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})

def register_view(request):
    # Capture plan from GET or POST to redirect after registration
    plan_name = request.GET.get('plan') or request.POST.get('plan')
    selected_plan = None
    
    if plan_name:
        selected_plan = Plan.objects.filter(name__iexact=plan_name).first()

    if request.method == 'POST':
        # Use HotelSignupForm for SaaS signup (has hotel_name)
        # For public guests (booking), use standard RegistrationForm
        # Logic: If plan is present, it's a SaaS signup.
        
        if plan_name:
             form = HotelSignupForm(request.POST)
        else:
             # Check if we are on a public tenant site or saas landing?
             # Assuming if NO plan and NO tenant, it's a generic signup (maybe for trial?)
             # But the user wants seamless hotel creation.
             # Let's default to HotelSignupForm if no tenant is set (SaaS mode)
             if not request.tenant or request.tenant.subdomain == 'public':
                 form = HotelSignupForm(request.POST)
             else:
                 form = RegistrationForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                # 1. Create User
                user = form.save()
                
                # 2. If Hotel Signup (SaaS), Create Tenant
                if isinstance(form, HotelSignupForm):
                    hotel_name = form.cleaned_data['hotel_name']
                    subdomain = form.cleaned_data.get('subdomain')
                    billing_cycle = form.cleaned_data.get('billing_cycle', 'monthly')
                    
                    if not subdomain:
                        subdomain = slugify(hotel_name)
                    else:
                        subdomain = slugify(subdomain)
                        
                    # Create Tenant
                    tenant = Tenant.objects.create(
                        name=hotel_name,
                        slug=subdomain,
                        subdomain=subdomain,
                        owner=user,
                        plan=selected_plan, # Can be None if not selected
                        # schema_name=subdomain, # Field does not exist in Tenant model
                        billing_cycle=billing_cycle
                    )
                    
                    # Create Domain
                    # domain_url = f"{subdomain}.localhost" # Dev environment
                    # Domain.objects.create(tenant=tenant, domain=domain_url, is_primary=True)
                    
                    # Create Owner Membership
                    Membership.objects.create(
                        user=user,
                        tenant=tenant,
                        role='OWNER',
                        is_active=True
                    )
                    
                    # Update User Role to Admin for this tenant context
                    # Although roles are handled by Membership for tenants, 
                    # updating the main user role ensures dashboard access logic works if it relies on user.role
                    user.role = User.Role.ADMIN
                    user.save()
                    
                    login(request, user)
                    
                    # Redirect logic
                    # If plan is paid, redirect to payment page
                    if selected_plan and selected_plan.price > 0:
                        tenant.is_active = False
                        tenant.subscription_status = 'pending_payment'
                        tenant.save()
                        
                        messages.info(request, "Please complete payment to activate your workspace.")
                        return redirect('tenant_payment', tenant_id=tenant.id)
                    else:
                        # Free plan: Activate immediately
                        tenant.is_active = True
                        tenant.subscription_status = 'active'
                        # Free forever or trial logic
                        tenant.subscription_end_date = timezone.now() + timedelta(days=365*10) 
                        tenant.save()
                    
                    # Redirect to Tenant Dashboard
                    protocol = 'https' if request.is_secure() else 'http'
                    
                    # Construct domain dynamically based on current host
                    current_host = request.get_host()
                    # Strip port if present for base domain logic
                    base_host = current_host.split(':')[0]
                    
                    # If we are on a subdomain (e.g. app.saas.com), we might want to strip 'app'
                    # But simpler: if localhost, use localhost. If saas.com, use saas.com
                    # We assume the current host IS the SaaS domain (e.g. localhost or saas.com)
                    
                    # Handle "www" or other prefixes if necessary, but usually just:
                    if 'localhost' in base_host:
                        root_domain = 'localhost'
                    else:
                        # Start from the end, take last 2 parts (e.g. domain.com)
                        # Or just use the current host as root if it's the landing page
                        root_domain = base_host

                    domain = f"{subdomain}.{root_domain}"
                    
                    # Add port back if it was on localhost/dev
                    if ':' in current_host:
                        port = current_host.split(':')[1]
                        domain = f"{domain}:{port}"
                        
                    dashboard_url = f"{protocol}://{domain}/dashboard/"
                    
                    # Send Welcome Email
                    try:
                        send_branded_email(
                            subject=f"Welcome to IHotel - {hotel_name} Created",
                            template_name='emails/welcome_hotel.html',
                            context={
                                'user': user,
                                'tenant': tenant,
                                'dashboard_url': dashboard_url,
                            },
                            recipient_list=[user.email],
                            tenant=None # Sent from Platform
                        )
                    except Exception as e:
                        print(f"Failed to send welcome email: {e}")
                    
                    return redirect(dashboard_url)
                
                # Standard User Signup (Guest)
                # Associate with current tenant if exists
                if request.tenant and request.tenant.subdomain != 'public':
                    Membership.objects.create(
                        user=user,
                        tenant=request.tenant,
                        role='GUEST', # Default role
                        is_active=True
                    )
                     
                    # Send Welcome Email
                    try:
                        protocol = 'https' if request.is_secure() else 'http'
                        host = request.get_host()
                        login_url = f"{protocol}://{host}/login/"
                         
                        send_branded_email(
                            subject=f"Welcome to {request.tenant.name}",
                            template_name='emails/welcome_user.html',
                            context={
                                'user': user,
                                'role': 'Member',
                                'login_url': login_url,
                            },
                            recipient_list=[user.email],
                            tenant=request.tenant
                        )
                    except Exception as e:
                        print(f"Failed to send welcome email: {e}")

                login(request, user)
                
                # Check purpose of visit
                visit_purpose = request.POST.get('visit_purpose', 'hotel')
                dashboard_url = reverse('dashboard')
                
                if visit_purpose == 'event':
                    return redirect(f'{dashboard_url}?welcome=event')
                elif visit_purpose == 'gym':
                    return redirect(f'{dashboard_url}?welcome=gym')
                    
                return redirect('dashboard')
        else:
            print("Registration Form Errors:", form.errors)
    else:
        # GET Request
        if not request.tenant or request.tenant.subdomain == 'public':
            form = HotelSignupForm()
        else:
            form = RegistrationForm()
        
    return render(request, 'accounts/register.html', {
        'form': form,
        'selected_plan': selected_plan
    })

def logout_view(request):
    logout(request)
    return redirect('home')

@login_required
def dashboard(request):
    user = request.user
    
    # Check Tenant Membership
    if request.tenant and not user.is_superuser:
        from tenants.models import Membership
        membership = Membership.objects.filter(user=user, tenant=request.tenant).first()
        
        if not membership:
             # Check if this user is the OWNER of this tenant (Edge case for newly created tenants)
             if request.tenant.owner == user:
                 # Auto-create Owner Membership if missing
                 Membership.objects.create(
                     user=user,
                     tenant=request.tenant,
                     role='OWNER',
                     is_active=True
                 )
                 # Refresh page to pick up new membership
                 return redirect('dashboard')
                 
             messages.error(request, "You are not a member of this hotel organization.")
             # Optionally create a default guest membership if it's a public hotel site?
             # For SaaS, usually strictly isolated. But for a hotel booking site, guests are welcome.
             # If role is GUEST, maybe allow?
             if user.role != User.Role.GUEST:
                 return redirect('home') 
    
    # Check for specific roles first before default guest fallback
    
    # Cleaner Dashboard
    if user.role == User.Role.CLEANER:
        # Get rooms assigned or just all cleaning rooms
        cleaning_rooms = Room.objects.filter(status=Room.Status.CLEANING)
        return render(request, 'accounts/dashboard_cleaner.html', {'cleaning_rooms': cleaning_rooms})

    # Kitchen Staff Dashboard
    if user.role == User.Role.KITCHEN:
        return redirect('staff_order_list')

    # Receptionist Dashboard
    if user.role == User.Role.RECEPTIONIST:
        # Focus on Today's Check-ins/outs
        today = timezone.now().date()
        
        check_ins = Booking.objects.filter(check_in_date__date=today, status=Booking.Status.CONFIRMED)
        check_outs = Booking.objects.filter(check_out_date__date=today, status=Booking.Status.CHECKED_IN)
        available_rooms_count = Room.objects.filter(status=Room.Status.AVAILABLE).count()
        
        context = {
            'check_ins': check_ins,
            'check_outs': check_outs,
            'available_rooms_count': available_rooms_count,
        }
        return render(request, 'accounts/dashboard_receptionist.html', context)

    # If not staff/superuser/admin/owner and not one of the special roles above, send to guest dashboard
    # NOTE: OWNER and ADMIN roles are string checks on the MEMBERSHIP, but user.role might be 'ADMIN' too if synced
    # If user is OWNER or ADMIN in the membership, they should proceed to the main dashboard logic below
    
    is_admin_or_owner = False
    if request.tenant:
        from tenants.models import Membership
        # We already fetched membership above if it exists, but let's be safe
        membership = Membership.objects.filter(user=user, tenant=request.tenant).first()
        if membership and membership.role in ['OWNER', 'ADMIN']:
            is_admin_or_owner = True
            
    if not user.is_staff and not user.is_superuser and not is_admin_or_owner:
        # Final check: Is this user the owner of the CURRENT tenant?
        # Sometimes role isn't synced yet if they just paid
        if request.tenant and request.tenant.owner == user:
             # Force them to admin dashboard
             return render(request, 'accounts/dashboard.html', context)
             
        guest_dashboard_url = reverse('guest_dashboard')
        welcome_param = request.GET.get('welcome')
        if welcome_param:
            return redirect(f"{guest_dashboard_url}?welcome={welcome_param}")
        return redirect('guest_dashboard')

    # Admin & Manager Dashboard (Full Stats)
    
    # Platform Admin Mode (Superuser on localhost)
    if not request.tenant and user.is_superuser:
        return redirect('platform_dashboard')

    # Gather Statistics
    # Filter by tenant if present
    tenant_filter = {'tenant': request.tenant} if request.tenant else {}
    
    total_guests = Booking.objects.filter(**tenant_filter).values('guest_email').distinct().count()
    
    # Invoice filtering
    # Invoice now has tenant field
    invoices = Invoice.objects.filter(**tenant_filter)
    
    # Filter out SUBSCRIPTION payments (platform fees) so tenant only sees their revenue
    # Assuming Invoice.Type.SUBSCRIPTION exists. If not, filter by booking__isnull=False or similar
    # But we added Type recently.
    if hasattr(Invoice, 'Type'):
         invoices = invoices.exclude(invoice_type=Invoice.Type.SUBSCRIPTION)
         
    total_revenue = invoices.filter(
        status=Invoice.Status.PAID
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_bookings = Booking.objects.filter(**tenant_filter).count()
    
    # Room Status
    rooms = Room.objects.filter(**tenant_filter)
    total_rooms = rooms.count()
    occupied_rooms = rooms.filter(status=Room.Status.OCCUPIED).count()
    available_rooms = rooms.filter(status=Room.Status.AVAILABLE).count()
    
    # Recent Bookings
    recent_bookings = Booking.objects.filter(**tenant_filter).select_related('room', 'room__room_type').order_by('-created_at')[:5]

    # Dynamic Data for Charts
    # Occupancy Trends (Last 7 Days vs Previous 7 Days)
    today = timezone.now().date()
    start_of_week = today - timedelta(days=today.weekday()) # Monday
    last_week_start = start_of_week - timedelta(days=7)
    
    occupancy_data = {
        'this_week': [],
        'last_week': []
    }
    
    # Calculate daily occupancy for this week
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        # Count rooms booked for this specific day
        count = Booking.objects.filter(
            **tenant_filter,
            check_in_date__date__lte=day,
            check_out_date__date__gt=day,
            status__in=[Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN]
        ).count()
        occupancy_data['this_week'].append(count)
        
    # Calculate daily occupancy for last week
    for i in range(7):
        day = last_week_start + timedelta(days=i)
        count = Booking.objects.filter(
            **tenant_filter,
            check_in_date__date__lte=day,
            check_out_date__date__gt=day,
            status__in=[Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN]
        ).count()
        occupancy_data['last_week'].append(count)

    # Revenue Overview (Last 7 Days)
    revenue_data = {
        'days': [],
        'amounts': [],
        'total_7_days': 0
    }
    
    for i in range(7):
        day = today - timedelta(days=6-i) # 6 days ago to today
        revenue_data['days'].append(day.strftime("%a")) # Mon, Tue, etc.
        
        daily_revenue = invoices.filter(
            status=Invoice.Status.PAID,
            issued_date__date=day
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        revenue_data['amounts'].append(float(daily_revenue))
        revenue_data['total_7_days'] += daily_revenue

    context = {
        'total_guests': total_guests,
        'total_revenue': total_revenue,
        'total_bookings': total_bookings,
        'total_rooms': total_rooms,
        'occupied_rooms': occupied_rooms,
        'available_rooms': available_rooms,
        'recent_bookings': recent_bookings,
        'is_platform_admin': False,
        'occupancy_data': occupancy_data,
        'revenue_data': revenue_data,
        'occupancy_max': max(max(occupancy_data['this_week'], default=0), max(occupancy_data['last_week'], default=0), 10), # For chart scaling
        'revenue_max': max(revenue_data['amounts'], default=1000),
    }
    
    return render(request, 'accounts/dashboard.html', context)

@login_required
def guest_dashboard(request):
    if request.user.is_staff:
        return redirect('dashboard')
        
    # Set visit purpose in session if provided, otherwise get from session
    welcome_param = request.GET.get('welcome')
    if welcome_param in ['event', 'gym', 'hotel']:
        request.session['visit_purpose'] = welcome_param
    else:
        welcome_param = request.session.get('visit_purpose')
    
    # Auto-detect guest type if not set
    if not welcome_param:
        has_active_gym = GymMembership.objects.filter(user=request.user, status='ACTIVE').exists()
        has_event = EventBooking.objects.filter(user=request.user, status__in=['CONFIRMED', 'PENDING']).exists()
        has_hotel = Booking.objects.filter(user=request.user, status__in=['CONFIRMED', 'CHECKED_IN', 'PENDING']).exists()
        
        if has_active_gym and not has_hotel and not has_event:
             welcome_param = 'gym'
        elif has_event and not has_hotel:
             welcome_param = 'event'
        else:
             welcome_param = 'hotel' # Default
             
        request.session['visit_purpose'] = welcome_param
    
    # Guest Stats
    bookings = Booking.objects.filter(user=request.user)
    total_bookings = bookings.count()
    active_bookings = bookings.filter(status__in=[Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN, Booking.Status.PENDING]).count()
    
    # Calculate Total Spent (Bookings + Room Service Orders)
    booking_spent = bookings.aggregate(total=Sum('total_price'))['total'] or 0
    
    # Sum of all non-cancelled orders
    order_spent = GuestOrder.objects.filter(
        user=request.user
    ).exclude(
        status='CANCELLED'
    ).aggregate(total=Sum('total_price'))['total'] or 0
    
    total_spent = booking_spent + order_spent
    
    recent_bookings = bookings.order_by('-created_at')[:3]
    
    # Event Bookings
    event_bookings = EventBooking.objects.filter(user=request.user).order_by('-created_at')
    
    # Gym Memberships
    gym_memberships = GymMembership.objects.filter(user=request.user).order_by('-end_date')
    
    # Recent Transactions (Paid Invoices)
    # We want to show a combined list of payments for bookings, events, and gym
    from billing.models import Payment
    recent_transactions = Payment.objects.filter(
        invoice__booking__user=request.user
    ) | Payment.objects.filter(
        invoice__event_booking__user=request.user
    ) | Payment.objects.filter(
        invoice__gym_membership__user=request.user
    )
    recent_transactions = recent_transactions.distinct().order_by('-payment_date')[:10]

    context = {
        'total_bookings': total_bookings,
        'active_bookings': active_bookings,
        'total_spent': total_spent,
        'recent_bookings': recent_bookings,
        'event_bookings': event_bookings,
        'gym_memberships': gym_memberships,
        'recent_transactions': recent_transactions,
        'welcome_mode': welcome_param,
    }
    return render(request, 'accounts/guest_dashboard.html', context)

@login_required
def profile(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name')
        user.last_name = request.POST.get('last_name')
        user.email = request.POST.get('email')
        user.phone_number = request.POST.get('phone_number')
        
        # Handle Password Change if provided
        new_password = request.POST.get('new_password')
        if new_password:
            user.set_password(new_password)
            login(request, user) # Re-login after password change
            
        user.save()
        return redirect('profile')
        
    return render(request, 'accounts/profile.html')

# User Management Views
class UserListView(TenantAdminRequiredMixin, ListView):
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    
    def get_queryset(self):
        # Strict Isolation: Only show users belonging to the current tenant
        # Users are linked to tenants via Membership
        if not self.request.tenant:
             return User.objects.none()
             
        from tenants.models import Membership
        # Get memberships for this tenant to access specific roles
        # Use select_related to fetch user data efficiently
        memberships = Membership.objects.filter(tenant=self.request.tenant).select_related('user')
        
        # We need to return User objects but with the specific tenant role attached
        # because the user.role field is global/default, but we want the tenant-specific role
        
        users = []
        for m in memberships:
            u = m.user
            # Dynamically attach the role from the membership to the user object for display
            u.tenant_role = m.role 
            users.append(u)
            
        return users

class UserCreateView(TenantAdminRequiredMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('user_list')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill role from Membership
        if self.request.tenant and self.object:
            from tenants.models import Membership
            membership = Membership.objects.filter(user=self.object, tenant=self.request.tenant).first()
            if membership:
                initial['role'] = membership.role
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        
        # Update Membership role
        if self.request.tenant:
            from tenants.models import Membership
            Membership.objects.update_or_create(
                user=user,
                tenant=self.request.tenant,
                defaults={'role': form.cleaned_data.get('role', 'GUEST')}
            )
            messages.success(self.request, "User updated successfully.")
        return response

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill role from Membership
        if self.request.tenant and self.object:
            from tenants.models import Membership
            membership = Membership.objects.filter(user=self.object, tenant=self.request.tenant).first()
            if membership:
                initial['role'] = membership.role
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        
        # Update Membership role
        if self.request.tenant:
            from tenants.models import Membership
            Membership.objects.update_or_create(
                user=user,
                tenant=self.request.tenant,
                defaults={'role': form.cleaned_data.get('role', 'GUEST')}
            )
            messages.success(self.request, "User updated successfully.")
        return response

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill role from Membership
        if self.request.tenant and self.object:
            from tenants.models import Membership
            membership = Membership.objects.filter(user=self.object, tenant=self.request.tenant).first()
            if membership:
                initial['role'] = membership.role
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        
        # Update Membership role
        if self.request.tenant:
            from tenants.models import Membership
            Membership.objects.update_or_create(
                user=user,
                tenant=self.request.tenant,
                defaults={'role': form.cleaned_data.get('role', 'GUEST')}
            )
            messages.success(self.request, "User updated successfully.")
        return response

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        
        # Create Membership for the current tenant
        if self.request.tenant:
            from tenants.models import Membership
            Membership.objects.create(
                user=user,
                tenant=self.request.tenant,
                role=form.cleaned_data.get('role', 'GUEST'),
                is_active=True
            )
            messages.success(self.request, f"User {user.username} created successfully.")
        return response

class UserDeleteView(TenantAdminRequiredMixin, DeleteView):
    model = User
    template_name = 'accounts/user_confirm_delete.html'
    success_url = reverse_lazy('user_list')
    
    def get_queryset(self):
        # Strict Isolation: Ensure user belongs to this tenant before deleting
        if not self.request.tenant:
             return User.objects.none()
        from tenants.models import Membership
        tenant_members = Membership.objects.filter(tenant=self.request.tenant).values_list('user', flat=True)
        return User.objects.filter(id__in=tenant_members)

@login_required
def bulk_delete_users(request):
    if not request.user.is_staff or request.user.role not in ['ADMIN', 'MANAGER']:
        messages.error(request, "Access denied.")
        return redirect('user_list')
        
    if request.method == 'POST':
        user_ids = request.POST.getlist('selected_users')
        if user_ids:
            # Prevent deleting self
            user_ids = [uid for uid in user_ids if int(uid) != request.user.id]
            
            deleted_count, _ = User.objects.filter(id__in=user_ids).delete()
            messages.success(request, f"Successfully deleted {deleted_count} users.")
        else:
            messages.warning(request, "No users selected for deletion.")
            
    return redirect('user_list')

class UserUpdateView(TenantAdminRequiredMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('user_list')
    
    def get_queryset(self):
        # Strict Isolation
        if not self.request.tenant:
             return User.objects.none()
        from tenants.models import Membership
        tenant_members = Membership.objects.filter(tenant=self.request.tenant).values_list('user', flat=True)
        return User.objects.filter(id__in=tenant_members)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        # Pre-fill role from Membership
        if self.request.tenant and self.object:
            from tenants.models import Membership
            membership = Membership.objects.filter(user=self.object, tenant=self.request.tenant).first()
            if membership:
                initial['role'] = membership.role
        return initial

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        
        # Update Membership role
        if self.request.tenant:
            from tenants.models import Membership
            Membership.objects.update_or_create(
                user=user,
                tenant=self.request.tenant,
                defaults={'role': form.cleaned_data.get('role', 'GUEST')}
            )
            messages.success(self.request, "User updated successfully.")
        return response
