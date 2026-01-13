from django.db.models.signals import post_save
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from core.email_utils import send_tenant_email
from django.conf import settings
from .models import Notification, AuditLog
from .utils import log_audit, get_client_ip

@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    tenant = getattr(request, 'tenant', None)
    AuditLog.objects.create(
        tenant=tenant,
        user=user,
        action=AuditLog.Action.LOGIN,
        module='Auth',
        details="User logged in",
        ip_address=get_client_ip(request)
    )

@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    if user:
        tenant = getattr(request, 'tenant', None)
        AuditLog.objects.create(
            tenant=tenant,
            user=user,
            action=AuditLog.Action.LOGOUT,
            module='Auth',
            details="User logged out",
            ip_address=get_client_ip(request)
        )

@receiver(post_save, sender=Notification)
def send_notification_email(sender, instance, created, **kwargs):
    if created and instance.recipient and instance.recipient.email:
        try:
            send_tenant_email(
                subject=f"Notification: {instance.title}",
                message=f"{instance.message}\n\nLink: {settings.SITE_URL if hasattr(settings, 'SITE_URL') else ''}{instance.link or ''}",
                recipient_list=[instance.recipient.email],
                tenant=instance.tenant,
                fail_silently=True,
            )
            print(f"Email sent to {instance.recipient.email}")
        except Exception as e:
            print(f"Failed to send email: {e}")
