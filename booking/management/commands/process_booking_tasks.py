from django.core.management.base import BaseCommand
from django.utils import timezone
import datetime
from booking.models import Booking
from hotel.models import Room
from core.models import Notification
from django.contrib.auth import get_user_model
from core.email_utils import send_branded_email, send_tenant_email
from django.urls import reverse
from django.conf import settings

User = get_user_model()

class Command(BaseCommand):
    help = 'Process booking auto-checkouts and send expiration reminders'

    def handle(self, *args, **options):
        self.stdout.write("Starting booking processing tasks...")
        self.cleanup_pending_bookings()
        self.process_auto_checkout()
        self.process_reminders()
        self.stdout.write("Completed booking processing tasks.")

    def cleanup_pending_bookings(self):
        """
        Auto-cancel PENDING bookings that are older than 30 minutes.
        This releases the room for other guests.
        """
        timeout_minutes = 30
        threshold = timezone.now() - datetime.timedelta(minutes=timeout_minutes)
        
        # Find PENDING bookings created before the threshold
        abandoned_bookings = Booking.objects.filter(
            status=Booking.Status.PENDING,
            created_at__lt=threshold
        )
        
        count = 0
        for booking in abandoned_bookings:
            try:
                booking.status = Booking.Status.CANCELLED
                booking.save()
                
                # Also cancel associated invoice if exists and pending
                # Assuming Invoice model has a foreign key to booking
                if hasattr(booking, 'invoices'):
                    for invoice in booking.invoices.filter(status='PENDING'): # string check or use enum if imported
                         invoice.status = 'CANCELLED'
                         invoice.save()
                
                count += 1
                self.stdout.write(self.style.WARNING(f'Auto-cancelled abandoned booking {booking.id}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error cancelling booking {booking.id}: {str(e)}'))
                
        if count > 0:
            self.stdout.write(self.style.SUCCESS(f'Successfully cleaned up {count} abandoned bookings'))

        now = timezone.now()
        # Find bookings that are CHECKED_IN but past their checkout time
        expired_bookings = Booking.objects.filter(
            status=Booking.Status.CHECKED_IN,
            check_out_date__lt=now
        )
        
        count = 0
        for booking in expired_bookings:
            try:
                # Mark booking as CHECKED_OUT
                booking.status = Booking.Status.CHECKED_OUT
                booking.save()
                
                # Update Room status to CLEANING
                room = booking.room
                room.status = Room.Status.CLEANING
                room.save()
                
                # Notify Guest
                self.notify_guest_checkout(booking)
                
                count += 1
                self.stdout.write(self.style.SUCCESS(f'Checked out booking {booking.id} for Room {room.room_number}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing booking {booking.id}: {str(e)}'))
            
        if count > 0:
            self.stdout.write(self.style.SUCCESS(f'Successfully auto-checked out {count} bookings'))
        else:
            self.stdout.write("No expired bookings found.")

    def process_reminders(self):
        now = timezone.now()
        
        # Define reminder intervals (hours before checkout)
        # 5 intervals as requested
        intervals = [
            (24, "24 hours"),
            (12, "12 hours"),
            (6, "6 hours"),
            (3, "3 hours"),
            (1, "1 hour")
        ]
        
        reminded_count = 0
        
        for hours, label in intervals:
            # Time window: Checkouts occurring between (Now + hours) and (Now + hours + window)
            # Window size depends on how often this script runs. Assuming hourly or more frequent.
            # To be safe and idempotent, we check if a notification of this type ALREADY exists for this booking.
            
            # Target time is roughly now + hours
            # Let's look for bookings expiring in the next (hours + 1) hours but greater than hours
            # Actually, better logic: Find bookings expiring in < hours + 1 and > hours - 1 (approx)
            # OR simpler: Check status.
            
            # Let's just iterate all active bookings and check time diff
            active_bookings = Booking.objects.filter(
                status__in=[Booking.Status.CHECKED_IN, Booking.Status.CONFIRMED],
                check_out_date__gt=now
            )
            
            for booking in active_bookings:
                time_left = booking.check_out_date - now
                hours_left = time_left.total_seconds() / 3600
                
                # Check if this booking falls into the current interval bucket
                # We give a tolerance window, e.g., +/- 0.5 hour or check if we passed the threshold recently
                # But since this might run periodically, we just check if hours_left is LESS than the threshold 
                # AND we haven't sent THIS specific reminder yet.
                
                if hours_left <= hours:
                    # Check if we already sent THIS specific reminder
                    title = f"Checkout Reminder: {label} left"
                    
                    already_sent = False
                    if booking.user:
                        already_sent = Notification.objects.filter(
                            recipient=booking.user,
                            title=title,
                            message__contains=f"#{booking.id}"
                        ).exists()
                    
                    # For email-only guests, we can't easily check DB unless we log emails. 
                    # For now, we'll skip duplicate check for guest-only if no user attached (or we could add a log model)
                    # To prevent spamming guest-only users every run, we could assume if hours_left is significantly less than hours (e.g. > 1h passed), we skip.
                    # But simpler is: "Is hours_left close to hours?"
                    # Let's use a window: hours_left is between (hours - 1) and hours.
                    
                    is_in_window = (hours - 1.5) <= hours_left <= hours
                    
                    if is_in_window and not already_sent:
                        try:
                            self.send_reminder(booking, label)
                            reminded_count += 1
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f'Error reminding booking {booking.id}: {str(e)}'))

        if reminded_count > 0:
            self.stdout.write(self.style.SUCCESS(f'Sent reminders for {reminded_count} bookings'))
        else:
            self.stdout.write("No new reminders needed.")

    def notify_guest_checkout(self, booking):
        if booking.user:
            Notification.objects.create(
                recipient=booking.user,
                tenant=booking.tenant,
                title="Auto Checked Out",
                message=f"Your stay at Room {booking.room.room_number} has ended. We hope you enjoyed your stay!",
                notification_type=Notification.Type.INFO
            )
        
        # Send Email
        if booking.guest_email:
            try:
                # Using send_tenant_email for simple text or send_branded_email if template exists
                # Fallback to simple text if template not found (simulated)
                send_tenant_email(
                    subject="Check-out Confirmation",
                    message=f"Dear {booking.guest_name},\n\nYour stay at Room {booking.room.room_number} has officially ended. We hope you had a pleasant stay!\n\nBest regards,\nHotel Management",
                    recipient_list=[booking.guest_email],
                    tenant=booking.tenant
                )
            except Exception as e:
                print(f"Failed to send email: {e}")

    def send_reminder(self, booking, time_label="soon"):
        # Create Dashboard Notification
        # We need a way to generate the URL. 
        # Since this is a command, we can't easily get request.build_absolute_uri
        # We'll just store the path.
        extend_url = f"/booking/{booking.id}/extend/"
        
        if booking.user:
            Notification.objects.create(
                recipient=booking.user,
                tenant=booking.tenant,
                title=f"Checkout Reminder: {time_label} left",
                message=f"Your booking #{booking.id} expires in {time_label}. Would you like to extend your stay?",
                notification_type=Notification.Type.WARNING,
                link=extend_url
            )
        
        self.send_reminder_email(booking, extend_url, time_label)

    def send_reminder_email(self, booking, extend_url=None, time_label="soon"):
        if not booking.guest_email:
            return
            
        if not extend_url:
            extend_url = f"/booking/{booking.id}/extend/"
            
        try:
            message = f"Dear {booking.guest_name},\n\nYour stay is ending in {time_label}. If you would like to extend your stay, please visit your dashboard or click here: {extend_url}\n\nBest regards,\nHotel Management"
            
            send_tenant_email(
                subject=f"Checkout Reminder: {time_label} left",
                message=message,
                recipient_list=[booking.guest_email],
                tenant=booking.tenant
            )
        except Exception as e:
            print(f"Failed to send reminder email: {e}")
