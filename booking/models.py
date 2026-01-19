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

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='bookings', null=True)
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
    
    # New Booking Reference System
    booking_reference = models.CharField(max_length=50, unique=True, blank=True, null=True, help_text="Unique booking ID per tenant")
    sequence_number = models.PositiveIntegerField(default=0, help_text="Sequential number for this tenant's bookings")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def duration_days(self):
        days = (self.check_out_date - self.check_in_date).days
        return days if days > 0 else 1

    @property
    def booking_id(self):
        """
        Returns the standardized booking reference ID.
        If booking_reference is set, return it.
        Otherwise, fall back to the old generation method (for legacy compatibility before save).
        """
        if self.booking_reference:
            return self.booking_reference
            
        # Fallback (similar to save logic but without saving)
        prefix = "HMS"
        if self.tenant:
            try:
                # Import here to avoid circular dependency
                from core.models import TenantSetting
                settings = TenantSetting.objects.filter(tenant=self.tenant).first()
                
                # Priority 1: Configured Prefix
                if settings and settings.booking_id_prefix:
                    prefix = settings.booking_id_prefix
                
                # Priority 2: Acronym from Hotel Name (TenantSettings)
                elif settings and settings.hotel_name:
                    words = settings.hotel_name.split()
                    acronym = "".join(w[0] for w in words if w and w[0].isalnum()).upper()
                    if len(acronym) >= 2:
                        prefix = acronym
                    else:
                        prefix = settings.hotel_name[:3].upper()
                        
                # Priority 3: Acronym from Tenant Name
                elif self.tenant.name:
                    words = self.tenant.name.split()
                    acronym = "".join(w[0] for w in words if w and w[0].isalnum()).upper()
                    if acronym:
                        prefix = acronym
                    else:
                        prefix = "".join(c for c in self.tenant.name if c.isalnum()).upper()[:3]
            except Exception:
                pass
        
        # Use ID if available, else 0 (unsaved)
        # Note: This is legacy behavior, ideally booking_reference should always be populated on save
        seq = self.sequence_number if self.sequence_number > 0 else (self.id if self.id else 0)
        return f"{prefix}-{self.created_at.year if self.created_at else 'YYYY'}-{seq:06d}"

    def save(self, *args, **kwargs):
        if not self.booking_reference:
            # Generate Unique Booking Reference
            prefix = "HMS"
            if self.tenant:
                try:
                    from core.models import TenantSetting
                    settings = TenantSetting.objects.filter(tenant=self.tenant).first()
                    
                    # Priority 1: Configured Prefix
                    if settings and settings.booking_id_prefix:
                        prefix = settings.booking_id_prefix
                    
                    # Priority 2: Acronym from Hotel Name (TenantSettings)
                    elif settings and settings.hotel_name:
                        words = settings.hotel_name.split()
                        acronym = "".join(w[0] for w in words if w and w[0].isalnum()).upper()
                        if len(acronym) >= 2:
                            prefix = acronym
                        else:
                            prefix = settings.hotel_name[:3].upper()
                            
                    # Priority 3: Acronym from Tenant Name
                    elif self.tenant.name:
                        words = self.tenant.name.split()
                        acronym = "".join(w[0] for w in words if w and w[0].isalnum()).upper()
                        if acronym:
                            prefix = acronym
                        else:
                            prefix = "".join(c for c in self.tenant.name if c.isalnum()).upper()[:3]
                except Exception:
                    pass
            
            # Determine Sequence Number
            # We need to find the max sequence_number for THIS tenant
            if not self.sequence_number:
                max_seq = Booking.objects.filter(tenant=self.tenant).aggregate(models.Max('sequence_number'))['sequence_number__max']
                self.sequence_number = (max_seq or 0) + 1
            
            import datetime
            year = self.created_at.year if self.created_at else datetime.datetime.now().year
            
            self.booking_reference = f"{prefix}-{year}-{self.sequence_number:06d}"
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Booking {self.booking_id} - {self.guest_name or self.user.username}"
