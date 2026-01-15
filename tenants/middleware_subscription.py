from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages

class SubscriptionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Skip if no tenant context (Public/Platform)
        if not hasattr(request, 'tenant') or not request.tenant:
            return

        tenant = request.tenant
        
        # Skip for superusers (Platform Admins)
        if request.user.is_authenticated and request.user.is_superuser:
            return

        # Define exempt URLs (Payment pages, Logout, Public pages)
        exempt_urls = [
            reverse('tenant_payment', kwargs={'tenant_id': tenant.id}),
            reverse('process_payment', kwargs={'tenant_id': tenant.id}),
            reverse('logout'),
            reverse('home'), # Public homepage
            '/static/',
            '/media/',
        ]
        
        if request.path_info in exempt_urls or request.path.startswith('/static/') or request.path.startswith('/media/'):
            return

        # Check Subscription Status
        # If subscription is NOT active or past due (grace period logic can be added here)
        # For strict blocking: check end date
        if tenant.subscription_end_date and tenant.subscription_end_date < timezone.now():
            # If status is not explicitly 'canceled', we might allow read-only or grace period
            # But requirement says "no user is able to access the dashboard"
            
            # Allow access if within grace period (e.g. 3 days)? 
            # "make sure no user is able to access the dashboard" -> Strict.
            
            # Exception: Tenant Owner needs to pay
            # If current URL is NOT payment page, redirect
            payment_url = reverse('tenant_payment', kwargs={'tenant_id': tenant.id})
            
            if request.path != payment_url:
                messages.error(request, "Your subscription has expired. Please renew to continue accessing the dashboard.")
                return redirect(payment_url)
