from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from tenants.models import Tenant
from billing.models import Invoice, Payment
from core.email_utils import send_branded_email
import uuid

class Command(BaseCommand):
    help = 'Process automatic renewals for expired subscriptions'

    def handle(self, *args, **kwargs):
        now = timezone.now()
        # Find tenants whose subscription has expired (or is about to expire today)
        # and have auto-renew enabled
        expired_tenants = Tenant.objects.filter(
            subscription_end_date__lte=now,
            auto_renew=True,
            is_active=True,
            plan__isnull=False
        ).exclude(payment_auth_code__isnull=True).exclude(payment_auth_code='')

        count = 0
        for tenant in expired_tenants:
            self.stdout.write(f"Processing renewal for {tenant.name}...")
            
            # Simulate Payment Processing with Auth Code
            # In real life: call gateway.charge_authorization(tenant.payment_auth_code, amount)
            success = True # Mock success
            
            if success:
                # Calculate Amount
                amount = tenant.plan.price
                if tenant.billing_cycle == 'yearly':
                    amount *= 12
                
                # Create Invoice
                invoice = Invoice.objects.create(
                    tenant=tenant,
                    amount=amount,
                    status=Invoice.Status.PAID,
                    invoice_type=Invoice.Type.SUBSCRIPTION,
                    due_date=now.date()
                )
                
                # Create Payment
                Payment.objects.create(
                    invoice=invoice,
                    amount=amount,
                    payment_method='AUTO_RENEW', # Or gateway name
                    transaction_id=f"AUTO-{uuid.uuid4().hex[:10]}",
                    payment_date=now
                )
                
                # Extend Subscription
                days = 365 if tenant.billing_cycle == 'yearly' else 30
                tenant.subscription_end_date = now + timedelta(days=days)
                tenant.subscription_status = 'active'
                tenant.save()
                
                # Send Email
                try:
                    send_branded_email(
                        subject=f"Subscription Renewed - {tenant.name}",
                        message=f"Your subscription for {tenant.plan.name} has been successfully renewed. Amount: {amount}",
                        recipient_list=[tenant.owner.email],
                        tenant=None
                    )
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to send email: {e}"))
                
                count += 1
                self.stdout.write(self.style.SUCCESS(f"Renewed {tenant.name}"))
            else:
                # Payment Failed logic
                tenant.subscription_status = 'past_due'
                tenant.save()
                self.stdout.write(self.style.WARNING(f"Payment failed for {tenant.name}"))

        self.stdout.write(self.style.SUCCESS(f"Successfully processed {count} renewals."))
