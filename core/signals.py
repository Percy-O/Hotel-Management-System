from django.db.models.signals import post_save
from django.dispatch import receiver
from core.email_utils import send_tenant_email
from django.conf import settings
from .models import Notification

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
