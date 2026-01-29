from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from .models import GymPlan, GymMembership, GymAttendance
from .forms import GymPlanForm, GymMembershipForm, StaffGymMembershipForm, PublicGymSignupForm

# --- Gym Plan Management (Manager Only) ---

class GymPlanListView(LoginRequiredMixin, ListView):
    model = GymPlan
    template_name = 'gym/plan_list.html'
    context_object_name = 'plans'

    def get_queryset(self):
        if self.request.user.is_staff:
            return GymPlan.objects.all()
        return GymPlan.objects.filter(is_active=True)

class PublicGymPlanListView(ListView):
    model = GymPlan
    template_name = 'gym/public_plan_list.html'
    context_object_name = 'plans'

    def get_queryset(self):
        queryset = GymPlan.objects.filter(is_active=True)
        if hasattr(self.request, 'tenant') and self.request.tenant:
            queryset = queryset.filter(tenant=self.request.tenant)
        return queryset

class GymPlanCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = GymPlan
    form_class = GymPlanForm
    template_name = 'gym/plan_form.html'
    success_url = reverse_lazy('gym_plan_list')

    def test_func(self):
        # Check Module Limit
        if self.request.tenant and self.request.tenant.plan:
             if not self.request.tenant.plan.module_gym:
                 return False
                 
        return self.request.user.can_manage_gym

    def form_valid(self, form):
        if hasattr(self.request, 'tenant') and self.request.tenant:
            form.instance.tenant = self.request.tenant
            
        messages.success(self.request, "Gym Plan created successfully.")
        return super().form_valid(form)

class GymPlanUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = GymPlan
    form_class = GymPlanForm
    template_name = 'gym/plan_form.html'
    success_url = reverse_lazy('gym_plan_list')

    def test_func(self):
        return self.request.user.can_manage_gym

    def form_valid(self, form):
        messages.success(self.request, "Gym Plan updated successfully.")
        return super().form_valid(form)

class GymPlanDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = GymPlan
    template_name = 'gym/plan_confirm_delete.html'
    success_url = reverse_lazy('gym_plan_list')

    def test_func(self):
        return self.request.user.can_manage_gym

# --- Membership Management ---

class GymMembershipListView(LoginRequiredMixin, ListView):
    model = GymMembership
    template_name = 'gym/membership_list.html'
    context_object_name = 'memberships'
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.can_manage_gym:
            return qs # All members
        return qs.filter(user=self.request.user) # My memberships

class GymMembershipCreateView(LoginRequiredMixin, CreateView):
    model = GymMembership
    form_class = StaffGymMembershipForm
    template_name = 'gym/membership_form.html'
    success_url = reverse_lazy('gym_membership_list')

    def get_initial(self):
        initial = super().get_initial()
        plan_id = self.request.GET.get('plan')
        if plan_id:
            initial['plan'] = get_object_or_404(GymPlan, pk=plan_id)
        return initial

    def form_valid(self, form):
        from django.contrib.auth import get_user_model
        from django.utils.crypto import get_random_string
        from core.email_utils import send_branded_email
        
        User = get_user_model()
        
        # 1. Handle User Resolution
        user = None
        guest_email = form.cleaned_data.get('guest_email')
        
        if guest_email:
            try:
                user = User.objects.get(email=guest_email)
                messages.info(self.request, f"Linked to existing user: {user.username}")
            except User.DoesNotExist:
                # Create Guest User
                username = guest_email.split('@')[0]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                created_password = get_random_string(8)
                guest_name = form.cleaned_data.get('guest_name', 'Guest')
                guest_phone = form.cleaned_data.get('guest_phone', '')
                
                user = User.objects.create_user(
                    username=username,
                    email=guest_email,
                    password=created_password,
                    first_name=guest_name.split(' ')[0] if guest_name else 'Guest',
                    last_name=' '.join(guest_name.split(' ')[1:]) if guest_name and ' ' in guest_name else '',
                    phone_number=guest_phone,
                    role=User.Role.GUEST
                )
                
                # Send welcome email with credentials
                # (Skipped for brevity, assume similar to events)
                messages.success(self.request, f"Created new user for {guest_email}")
        else:
            # Fallback to current user if no guest email provided (Self-signup by staff?)
            # Or force error. For now, default to self but warn.
            if not form.cleaned_data.get('guest_email'):
                 messages.warning(self.request, "No guest email provided. Membership linked to your staff account.")
                 user = self.request.user

        plan = form.cleaned_data['plan']
        start_date = form.cleaned_data['start_date']
        
        # Calculate end date
        end_date = start_date + timedelta(days=plan.duration_days)
        
        form.instance.user = user
        form.instance.end_date = end_date
        form.instance.status = 'ACTIVE' # Set active by default for manual creation
        
        messages.success(self.request, "Membership created successfully.")
        response = super().form_valid(form)
        
        # Create Invoice (Paid)
        from billing.models import Invoice
        Invoice.objects.create(
            gym_membership=form.instance,
            amount=plan.price,
            status=Invoice.Status.PAID, # Assumed paid at desk
            due_date=timezone.now().date()
        )
        
        # Create Notification
        from core.models import Notification
        Notification.objects.create(
            recipient=user,
            title="Gym Membership Activated",
            message=f"Your membership for {plan.name} is now active until {end_date.strftime('%Y-%m-%d')}.",
            notification_type='SUCCESS',
            link=reverse_lazy('gym_membership_detail', kwargs={'pk': form.instance.pk})
        )
        return response

class GymMembershipDetailView(LoginRequiredMixin, DetailView):
    model = GymMembership
    template_name = 'gym/membership_detail.html'
    context_object_name = 'membership'

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.can_manage_gym:
            return qs
        return qs.filter(user=self.request.user)

@login_required
def cancel_membership(request, pk):
    membership = get_object_or_404(GymMembership, pk=pk)
    
    # Allow user to cancel own membership or staff to cancel any
    if request.user != membership.user and not request.user.can_manage_gym:
        messages.error(request, "Permission denied.")
        return redirect('gym_membership_list')
        
    membership.status = 'CANCELLED'
    membership.save()
    messages.success(request, "Membership cancelled successfully.")
    
    # Create Notification
    from core.models import Notification
    Notification.objects.create(
        recipient=membership.user,
        title="Gym Membership Cancelled",
        message=f"Your membership for {membership.plan.name} has been cancelled.",
        notification_type='WARNING',
        link=reverse_lazy('gym_membership_detail', kwargs={'pk': membership.pk})
    )
    
    return redirect('gym_membership_list')

class PublicGymSignupView(CreateView):
    model = GymMembership
    form_class = PublicGymSignupForm
    template_name = 'gym/public_signup.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def get_initial(self):
        initial = super().get_initial()
        plan_id = self.request.GET.get('plan')
        if plan_id:
            initial['plan'] = get_object_or_404(GymPlan, pk=plan_id)
        return initial

    def form_valid(self, form):
        from django.contrib.auth import get_user_model, login
        from django.utils.crypto import get_random_string
        from billing.models import Invoice
        
        User = get_user_model()
        user = self.request.user
        
        if not user.is_authenticated:
            email = form.cleaned_data['email']
            full_name = form.cleaned_data['full_name']
            phone_number = form.cleaned_data['phone_number']
            
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                username = email.split('@')[0]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                password = get_random_string(8)
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=full_name.split(' ')[0],
                    last_name=' '.join(full_name.split(' ')[1:]) if ' ' in full_name else '',
                    phone_number=phone_number,
                    role=User.Role.GUEST
                )
                login(self.request, user)
        
        plan = form.cleaned_data['plan']
        start_date = form.cleaned_data['start_date']
        end_date = start_date + timedelta(days=plan.duration_days)
        
        form.instance.user = user
        form.instance.end_date = end_date
        form.instance.status = 'PENDING'
        
        # Manually save instead of calling super().form_valid(form)
        self.object = form.save()
        
        # Create Invoice
        Invoice.objects.create(
            gym_membership=self.object,
            amount=plan.price,
            status=Invoice.Status.PENDING,
            due_date=timezone.now().date(),
            tenant=self.request.tenant if hasattr(self.request, 'tenant') else None
        )
        
        return redirect('payment_selection', invoice_id=self.object.invoices.first().pk)

@login_required
def gym_check_in(request):
    # Find active membership
    membership = GymMembership.objects.filter(
        user=request.user, 
        status='ACTIVE',
        end_date__gte=timezone.now().date()
    ).first()
    
    if not membership:
        messages.error(request, "No active gym membership found.")
        return redirect('dashboard')
        
    # Check if already checked in today/currently
    active_attendance = GymAttendance.objects.filter(membership=membership, check_out__isnull=True).first()
    if active_attendance:
        messages.warning(request, "You are already checked in.")
    else:
        GymAttendance.objects.create(membership=membership)
        messages.success(request, "Checked in to Gym successfully.")
        
    return redirect('dashboard')

@login_required
def gym_check_out(request):
    membership = GymMembership.objects.filter(user=request.user).first() # Simplify lookup
    if not membership:
        return redirect('dashboard')
        
    active_attendance = GymAttendance.objects.filter(membership__user=request.user, check_out__isnull=True).first()
    if active_attendance:
        active_attendance.check_out = timezone.now()
        active_attendance.save()
        messages.success(request, "Checked out from Gym.")
    else:
        messages.info(request, "You were not checked in.")
        
    return redirect('dashboard')
