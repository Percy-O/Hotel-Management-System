from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView, FormView
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q
from .forms import TenantForm, PlanForm
from .payment_forms import PaymentGatewayForm
from .models import Tenant, Domain, Membership, Plan
from billing.models import PaymentGateway, Payment
from core.models import GlobalSetting
from core.forms import GlobalSettingForm
from django.contrib.auth import get_user_model

User = get_user_model()

def is_superuser(user):
    return user.is_superuser

class SuperUserRequiredMixin:
    @method_decorator(user_passes_test(is_superuser))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

# --- Finance Management ---
class PlatformPaymentListView(SuperUserRequiredMixin, ListView):
    model = Payment
    template_name = 'platform/payment_list.html'
    context_object_name = 'payments'
    paginate_by = 20
    
    def get_queryset(self):
        return Payment.objects.all().order_by('-payment_date')

class PlatformFinanceSettingsView(SuperUserRequiredMixin, TemplateView):
    template_name = 'platform/finance_settings.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['paystack'] = PaymentGateway.objects.filter(tenant=None, name='PAYSTACK').first()
        context['flutterwave'] = PaymentGateway.objects.filter(tenant=None, name='FLUTTERWAVE').first()
        return context

# --- Audit Logs ---
class PlatformLogListView(SuperUserRequiredMixin, TemplateView):
    template_name = 'platform/log_list.html'
    # Placeholder for actual logging system

# --- Platform Settings (Payments) ---
class PlatformSettingsView(SuperUserRequiredMixin, UpdateView):
    template_name = 'platform/settings.html'
    model = GlobalSetting
    form_class = GlobalSettingForm
    success_url = reverse_lazy('platform_settings')
    
    def get_object(self, queryset=None):
        return GlobalSetting.load()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Fetch Platform Gateways (tenant=None)
        context['paystack'] = PaymentGateway.objects.filter(tenant=None, name='PAYSTACK').first()
        context['flutterwave'] = PaymentGateway.objects.filter(tenant=None, name='FLUTTERWAVE').first()
        return context
    
    def form_valid(self, form):
        messages.success(self.request, "Global email settings updated successfully.")
        return super().form_valid(form)

class PlatformGatewayUpdateView(SuperUserRequiredMixin, FormView):
    template_name = 'platform/gateway_form.html'
    form_class = PaymentGatewayForm
    success_url = reverse_lazy('platform_settings')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        provider = self.kwargs.get('provider') # 'paystack' or 'flutterwave'
        provider_key = 'PAYSTACK' if provider == 'paystack' else 'FLUTTERWAVE'
        
        self.instance = PaymentGateway.objects.filter(tenant=None, name=provider_key).first()
        if self.instance:
            kwargs['instance'] = self.instance
        return kwargs

    def form_valid(self, form):
        gateway = form.save(commit=False)
        gateway.tenant = None # Ensure it's platform level
        gateway.save()
        messages.success(self.request, f"{gateway.get_name_display()} settings updated.")
        return super().form_valid(form)

# --- Platform Dashboard ---
@login_required
@user_passes_test(is_superuser)
def platform_dashboard(request):
    context = {
        'total_tenants': Tenant.objects.count(),
        'active_tenants': Tenant.objects.filter(is_active=True).count(),
        'total_users': User.objects.count(),
        'total_revenue': 125000, # Placeholder or aggregate from Invoice
        'recent_tenants': Tenant.objects.order_by('-created_at')[:5],
        'recent_users': User.objects.order_by('-date_joined')[:5],
    }
    return render(request, 'platform/dashboard.html', context)

# --- Tenant Management ---
class TenantListView(SuperUserRequiredMixin, ListView):
    model = Tenant
    template_name = 'platform/tenant_list.html'
    context_object_name = 'tenants'
    paginate_by = 10

    def get_queryset(self):
        query = self.request.GET.get('q')
        queryset = Tenant.objects.all().order_by('-created_at')
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | 
                Q(subdomain__icontains=query) |
                Q(owner__email__icontains=query)
            )
        return queryset

class TenantUpdateView(SuperUserRequiredMixin, UpdateView):
    model = Tenant
    fields = ['name', 'subdomain', 'plan', 'is_active', 'logo']
    template_name = 'platform/tenant_form.html'
    success_url = reverse_lazy('platform_tenant_list')

    def form_valid(self, form):
        messages.success(self.request, "Tenant updated successfully.")
        return super().form_valid(form)

class TenantDeleteView(SuperUserRequiredMixin, DeleteView):
    model = Tenant
    template_name = 'platform/tenant_confirm_delete.html'
    success_url = reverse_lazy('platform_tenant_list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Tenant deleted successfully.")
        return super().delete(request, *args, **kwargs)

# --- User Management (Platform Level) ---
class PlatformUserListView(SuperUserRequiredMixin, ListView):
    model = User
    template_name = 'platform/user_list.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        query = self.request.GET.get('q')
        queryset = User.objects.all().order_by('-date_joined')
        if query:
            queryset = queryset.filter(
                Q(username__icontains=query) | 
                Q(email__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            )
        return queryset

# --- Plan Management ---
class PlanListView(SuperUserRequiredMixin, ListView):
    model = Plan
    template_name = 'platform/plan_list.html'
    context_object_name = 'plans'

class PlanCreateView(SuperUserRequiredMixin, CreateView):
    model = Plan
    form_class = PlanForm
    template_name = 'platform/plan_form.html'
    success_url = reverse_lazy('platform_subscriptions')

    def form_valid(self, form):
        messages.success(self.request, "Plan created successfully.")
        return super().form_valid(form)

class PlanUpdateView(SuperUserRequiredMixin, UpdateView):
    model = Plan
    form_class = PlanForm
    template_name = 'platform/plan_form.html'
    success_url = reverse_lazy('platform_subscriptions')

from django.views.generic import DetailView

class PlanDetailView(SuperUserRequiredMixin, DetailView):
    model = Plan
    template_name = 'platform/plan_detail.html'
    context_object_name = 'plan'
