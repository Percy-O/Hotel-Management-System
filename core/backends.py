from django.core.mail.backends.smtp import EmailBackend
from django.conf import settings
from .models import GlobalSetting

class DatabaseEmailBackend(EmailBackend):
    def __init__(self, host=None, port=None, username=None, password=None,
                 use_tls=None, fail_silently=False, use_ssl=None, timeout=None,
                 ssl_keyfile=None, ssl_certfile=None,
                 **kwargs):
        
        # Try to fetch global settings
        try:
            global_settings = GlobalSetting.objects.first()
        except Exception:
            # Handling migrations or DB not ready
            global_settings = None

        if global_settings:
            # Only override if not explicitly passed (i.e. if None)
            # This allows send_tenant_email to pass specific tenant settings
            if host is None:
                host = global_settings.email_host or settings.EMAIL_HOST
            
            if port is None:
                port = global_settings.email_port or settings.EMAIL_PORT
                
            if username is None:
                username = global_settings.email_host_user or settings.EMAIL_HOST_USER
                
            if password is None:
                password = global_settings.email_host_password or settings.EMAIL_HOST_PASSWORD
            
            # Boolean fields need careful handling as False is a valid value
            # If passed explicitly (not None), use it. Else use DB.
            if use_tls is None:
                use_tls = global_settings.email_use_tls
            
            if use_ssl is None:
                use_ssl = global_settings.email_use_ssl
        
        super().__init__(host=host, port=port, username=username, password=password,
                         use_tls=use_tls, fail_silently=fail_silently, use_ssl=use_ssl,
                         timeout=timeout, ssl_keyfile=ssl_keyfile, ssl_certfile=ssl_certfile,
                         **kwargs)
