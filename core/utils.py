from .models import AuditLog

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def log_audit(request, action, module, details):
    """
    Creates an audit log entry.
    """
    if not request.user.is_authenticated:
        return

    tenant = getattr(request, 'tenant', None)
    
    AuditLog.objects.create(
        tenant=tenant,
        user=request.user,
        action=action,
        module=module,
        details=details,
        ip_address=get_client_ip(request)
    )
