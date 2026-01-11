from threading import local
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

_thread_locals = local()

def get_current_tenant():
    return getattr(_thread_locals, 'tenant', None)

def set_current_tenant(tenant):
    _thread_locals.tenant = tenant

def has_tenant_permission(user, tenant, required_roles):
    """
    Checks if user has a membership in the tenant with one of the required roles.
    """
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
        
    # Check membership
    # Avoid circular import by importing inside function if needed, or assume Membership is loaded
    from .models import Membership
    
    try:
        membership = Membership.objects.get(user=user, tenant=tenant, is_active=True)
        return membership.role in required_roles
    except Membership.DoesNotExist:
        return False

def tenant_role_required(roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.tenant:
                 messages.error(request, "No tenant context.")
                 return redirect('home')
            
            if has_tenant_permission(request.user, request.tenant, roles):
                return view_func(request, *args, **kwargs)
            else:
                messages.error(request, "You do not have permission to access this resource.")
                return redirect('dashboard')
        return _wrapped_view
    return decorator
