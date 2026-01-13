from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect
from django.contrib import messages
from .models import Membership

class TenantAdminRequiredMixin(UserPassesTestMixin):
    """
    Ensures the user is a member of the current tenant with ADMIN or MANAGER role.
    Superusers are exempt.
    """
    def test_func(self):
        user = self.request.user
        tenant = getattr(self.request, 'tenant', None)
        
        if not user.is_authenticated:
            return False
            
        if user.is_superuser:
            return True
            
        if not tenant:
            return False
            
        # Check Membership
        # Also check if user is the OWNER of the tenant (implicit admin)
        if tenant.owner == user:
            return True
            
        return Membership.objects.filter(
            user=user, 
            tenant=tenant, 
            role__in=['ADMIN', 'MANAGER', 'OWNER'], # Added OWNER explicitly
            is_active=True
        ).exists()

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "Access Denied: You are not an admin of this hotel.")
            return redirect('home')
        return redirect('login')
