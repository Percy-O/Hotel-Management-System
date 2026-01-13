from django.core.mail import EmailMessage, get_connection
from django.conf import settings
from .models import GlobalSetting, TenantSetting
from django.template.loader import render_to_string
from django.utils.html import strip_tags

def get_email_connection(tenant=None):
    """
    Returns an email connection based on tenant settings or global settings.
    """
    # Default to Django settings
    host = settings.EMAIL_HOST
    port = settings.EMAIL_PORT
    username = settings.EMAIL_HOST_USER
    password = settings.EMAIL_HOST_PASSWORD
    use_tls = settings.EMAIL_USE_TLS
    use_ssl = settings.EMAIL_USE_SSL
    
    # 1. Check Global Settings (Superadmin overrides)
    # We use .first() assuming there is only one global setting object
    global_settings = GlobalSetting.objects.first()
    if global_settings:
        host = global_settings.email_host or host
        port = global_settings.email_port or port
        username = global_settings.email_host_user or username
        password = global_settings.email_host_password or password
        use_tls = global_settings.email_use_tls
        use_ssl = global_settings.email_use_ssl

    # 2. Check Tenant Settings (if allowed and configured)
    if tenant and hasattr(tenant, 'plan') and tenant.plan and tenant.plan.allow_custom_email:
        try:
            tenant_settings = TenantSetting.objects.get(tenant=tenant)
            # Only override if the tenant has actually provided a host
            if tenant_settings.email_host: 
                host = tenant_settings.email_host
                port = tenant_settings.email_port
                username = tenant_settings.email_host_user
                password = tenant_settings.email_host_password
                use_tls = tenant_settings.email_use_tls
                use_ssl = tenant_settings.email_use_ssl
        except TenantSetting.DoesNotExist:
            pass

    try:
        connection = get_connection(
            host=host, 
            port=port, 
            username=username, 
            password=password, 
            use_tls=use_tls,
            use_ssl=use_ssl
        )
        return connection
    except Exception as e:
        print(f"Error creating email connection: {e}")
        return get_connection() # Fallback to default

def send_tenant_email(subject, message, recipient_list, tenant=None, html_message=None, from_email=None, fail_silently=True):
    """
    Sends an email using the appropriate connection.
    """
    connection = get_email_connection(tenant)
    
    # Determine Sender
    sender = settings.DEFAULT_FROM_EMAIL
    
    # Global Default
    global_settings = GlobalSetting.objects.first()
    if global_settings and global_settings.default_from_email:
        sender = global_settings.default_from_email
        
    # Tenant Override
    if tenant and hasattr(tenant, 'plan') and tenant.plan and tenant.plan.allow_custom_email:
        try:
            tenant_settings = TenantSetting.objects.get(tenant=tenant)
            if tenant_settings.default_from_email:
                sender = tenant_settings.default_from_email
        except TenantSetting.DoesNotExist:
            pass
            
    if from_email:
        sender = from_email

    email = EmailMessage(
        subject,
        message,
        sender,
        recipient_list,
        connection=connection,
    )
    if html_message:
        email.content_subtype = "html"
        email.body = html_message
        
    try:
        return email.send(fail_silently=fail_silently)
    except Exception as e:
        print(f"Error sending email: {e}")
        if not fail_silently:
            raise e
        return 0

def send_branded_email(subject, template_name, context, recipient_list, tenant=None, from_email=None, fail_silently=True):
    """
    Sends a branded HTML email.
    Wraps the content in a base template with appropriate logo/branding.
    """
    
    # 1. Determine Branding
    company_name = "IHotel"
    logo_url = None
    primary_color = "#3b82f6" # Blue-500
    
    if tenant:
        # Try TenantSetting first (CMS override)
        try:
            tenant_settings = TenantSetting.objects.get(tenant=tenant)
            company_name = tenant_settings.hotel_name or tenant.name
            if tenant_settings.hotel_logo:
                # Assuming you have a way to serve media files or use a CDN
                # For email, absolute URLs are best.
                # Here we might need request to build absolute URI, but let's try .url
                try:
                    logo_url = tenant_settings.hotel_logo.url
                except:
                    pass
            elif tenant.logo:
                try:
                    logo_url = tenant.logo.url
                except:
                    pass
            
            if tenant_settings.custom_primary_color:
                primary_color = tenant_settings.custom_primary_color
            elif tenant.primary_color:
                primary_color = tenant.primary_color
                
        except TenantSetting.DoesNotExist:
            # Fallback to Tenant model
            company_name = tenant.name
            if tenant.logo:
                try:
                    logo_url = tenant.logo.url
                except:
                    pass
            if tenant.primary_color:
                primary_color = tenant.primary_color

    # Add branding to context
    context['company_name'] = company_name
    context['logo_url'] = logo_url
    context['primary_color'] = primary_color
    context['subject'] = subject
    context['tenant'] = tenant

    # 2. Render Template
    html_message = render_to_string(template_name, context)
    plain_message = strip_tags(html_message)
    
    # 3. Send Email
    return send_tenant_email(
        subject=subject,
        message=plain_message,
        recipient_list=recipient_list,
        tenant=tenant,
        html_message=html_message,
        from_email=from_email,
        fail_silently=fail_silently
    )
