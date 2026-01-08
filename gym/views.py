from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from .models import GymPlan, GymMembership
from .forms import GymPlanForm, GymMembershipForm

# --- Gym Plan Management (Manager Only) ---

class GymPlanListView(LoginRequiredMixin, ListView):
    model = GymPlan
    template_name = 'gym/plan_list.html'
    context_object_name = 'plans'

    def get_queryset(self):
        if self.request.user.is_staff:
            return GymPlan.objects.all()
        return GymPlan.objects.filter(is_active=True)

class GymPlanCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = GymPlan
    form_class = GymPlanForm
    template_name = 'gym/plan_form.html'
    success_url = reverse_lazy('gym_plan_list')

    def test_func(self):
        return self.request.user.can_manage_gym

    def form_valid(self, form):
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
    form_class = GymMembershipForm
    template_name = 'gym/membership_form.html'
    success_url = reverse_lazy('gym_membership_list')

    def get_initial(self):
        initial = super().get_initial()
        plan_id = self.request.GET.get('plan')
        if plan_id:
            initial['plan'] = get_object_or_404(GymPlan, pk=plan_id)
        return initial

    def form_valid(self, form):
        plan = form.cleaned_data['plan']
        start_date = form.cleaned_data['start_date']
        
        # Calculate end date
        end_date = start_date + timedelta(days=plan.duration_days)
        
        form.instance.user = self.request.user
        form.instance.end_date = end_date
        form.instance.status = 'ACTIVE' # Set active by default for now
        
        messages.success(self.request, "Membership created successfully.")
        response = super().form_valid(form)
        
        # Create Invoice
        from billing.models import Invoice
        Invoice.objects.create(
            gym_membership=form.instance,
            amount=plan.price,
            status=Invoice.Status.PENDING,
            due_date=timezone.now().date()
        )
        
        # Create Notification
        from core.models import Notification
        Notification.objects.create(
            recipient=self.request.user,
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
