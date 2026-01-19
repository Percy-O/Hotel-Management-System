from django.db import models
from django.conf import settings
from decimal import Decimal
from django.utils import timezone

class EventHall(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='event_halls', null=True, blank=True)
    PRICING_TYPE_CHOICES = [
        ('PER_HOUR', 'Per Hour'),
        ('PER_DAY', 'Per Day'),
        ('PER_EVENT', 'Per Event'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, help_text="Detailed description of the hall")
    amenities = models.TextField(blank=True, help_text="Comma-separated list of amenities (e.g. WiFi, Projector, Sound System)")
    capacity = models.PositiveIntegerField(help_text="Maximum number of guests")
    pricing_type = models.CharField(max_length=20, choices=PRICING_TYPE_CHOICES, default='PER_HOUR')
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price based on selected pricing type", default=0.00)
    
    # Deprecated: Kept for migration, will remove later
    price_per_hour = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to='event_halls/', blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} (Cap: {self.capacity})"

class EventHallImage(models.Model):
    hall = models.ForeignKey(EventHall, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='event_halls/gallery/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.hall.name}"

import qrcode
from io import BytesIO
from django.core.files import File

class EventBooking(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='event_bookings')
    hall = models.ForeignKey(EventHall, on_delete=models.CASCADE, related_name='bookings')
    event_name = models.CharField(max_length=255, help_text="Title of the event")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    qr_code = models.ImageField(upload_to='event_qr_codes/', blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-calculate price if not set (simple logic)
        if not self.total_price and self.start_time and self.end_time:
            # Ensure price is Decimal
            hall_price = self.hall.price
            if not isinstance(hall_price, Decimal):
                hall_price = Decimal(str(hall_price))
            
            pricing_type = self.hall.pricing_type
            
            if pricing_type == 'PER_HOUR':
                # Calculate duration in hours as Decimal
                duration_seconds = Decimal(str((self.end_time - self.start_time).total_seconds()))
                duration_hours = duration_seconds / Decimal("3600")
                self.total_price = hall_price * duration_hours
                
            elif pricing_type == 'PER_DAY':
                # Calculate duration in days (rounding up partial days)
                duration_days = (self.end_time.date() - self.start_time.date()).days
                if duration_days < 1:
                    duration_days = 1
                self.total_price = hall_price * Decimal(str(duration_days))
                
            elif pricing_type == 'PER_EVENT':
                # Flat fee
                self.total_price = hall_price

        # Generate QR Code if confirmed and not yet generated
        if self.status == 'CONFIRMED' and not self.qr_code:
            qr_data = f"EVENT-BOOKING-{self.id}-{self.user.username}"
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            
            timestamp = self.created_at.timestamp() if self.created_at else timezone.now().timestamp()
            file_name = f'event_qr_{self.user.username}_{timestamp}.png'
            self.qr_code.save(file_name, File(buffer), save=False)
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.event_name} at {self.hall.name}"
