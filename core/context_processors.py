from .models import TenantSetting, Notification
from tenants.utils import get_current_tenant

def site_settings(request):
    tenant = getattr(request, 'tenant', None)
    settings_obj = None
    
    if tenant:
        settings_obj, created = TenantSetting.objects.get_or_create(tenant=tenant)
        # Ensure hotel name matches tenant name if default "My Hotel"
        if settings_obj.hotel_name == "My Hotel":
            settings_obj.hotel_name = tenant.name
            settings_obj.save()
    
    context = {'site_settings': settings_obj}
    
    if request.user.is_authenticated:
        # Get unread notifications for the user
        # Note: Scoping notifications to tenant is also important if user belongs to multiple
        # But Notification model doesn't have tenant yet.
        # Assuming notifications are user-bound, but if a user is in multiple tenants, 
        # we might want to filter notifications by tenant too.
        # For now, just user.
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        context['unread_notifications_count'] = count
    return context
