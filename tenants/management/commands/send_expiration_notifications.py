from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from tenants.models import Tenant
from core.models import Notification
from core.email_utils import send_tenant_email

class Command(BaseCommand):
    help = 'Sends subscription expiration notifications to tenants'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        
        # Define notification thresholds (days before expiration)
        thresholds = [7, 3, 1]
        
        for days in thresholds:
            target_date = today + timedelta(days=days)
            
            # Find tenants expiring on this target date
            expiring_tenants = Tenant.objects.filter(
                subscription_end_date__date=target_date,
                is_active=True,
                auto_renew=False # Only notify if they haven't set auto-renew (or notify anyway about charge)
            )
            
            for tenant in expiring_tenants:
                days_left = (tenant.subscription_end_date.date() - today).days
                
                # Send In-App Notification
                Notification.objects.create(
                    recipient=tenant.owner,
                    title="Subscription Expiring Soon",
                    message=f"Your subscription for {tenant.name} will expire in {days_left} days. Please renew to avoid service interruption.",
                    notification_type='warning',
                    link='/tenant/settings/' 
                )
                
                # Send Email
                self.stdout.write(f"Sending email to {tenant.owner.email} for tenant {tenant.name} (Expiring in {days_left} days)")
                
                try:
                    send_tenant_email(
                        subject="Subscription Expiration Warning",
                        message=f"Your plan for {tenant.name} expires in {days_left} days. Please renew to avoid service interruption.",
                        recipient_list=[tenant.owner.email],
                        tenant=None # Always use Global/Platform settings for billing emails
                    )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to send email: {e}"))

        self.stdout.write(self.style.SUCCESS('Successfully sent expiration notifications'))