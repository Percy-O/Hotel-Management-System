from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import Notification

@receiver(post_save, sender=Notification)
def send_notification_email(sender, instance, created, **kwargs):
    if created and instance.recipient and instance.recipient.email:
        try:
            send_mail(
                subject=f"Notification: {instance.title}",
                message=f"{instance.message}\n\nLink: {settings.SITE_URL if hasattr(settings, 'SITE_URL') else ''}{instance.link or ''}",
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[instance.recipient.email],
                fail_silently=True,
            )
            print(f"Email sent to {instance.recipient.email}")
        except Exception as e:
            print(f"Failed to send email: {e}")
