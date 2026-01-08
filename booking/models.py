from django.db import models
from django.conf import settings
from hotel.models import Room, Hotel

class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        CHECKED_IN = 'CHECKED_IN', 'Checked In'
        CHECKED_OUT = 'CHECKED_OUT', 'Checked Out'
        CANCELLED = 'CANCELLED', 'Cancelled'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings', null=True, blank=True)
    # For guests without accounts (walk-ins or guest checkout)
    guest_name = models.CharField(max_length=255, blank=True)
    guest_email = models.EmailField(blank=True)
    guest_phone = models.CharField(max_length=20, blank=True)
    
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='bookings')
    check_in_date = models.DateTimeField()
    check_out_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def duration_days(self):
        days = (self.check_out_date - self.check_in_date).days
        return days if days > 0 else 1

    @property
    def booking_id(self):
        """
        Returns a standardized booking reference ID (e.g., HMS-2026-000123)
        """
        return f"HMS-{self.created_at.year}-{self.id:06d}"

    def __str__(self):
        return f"Booking {self.booking_id} - {self.guest_name or self.user.username}"
