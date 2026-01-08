from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MANAGER = "MANAGER", "Manager"
        RECEPTIONIST = "RECEPTIONIST", "Receptionist"
        STAFF = "STAFF", "Staff"
        CLEANER = "CLEANER", "Cleaner"
        KITCHEN = "KITCHEN", "Kitchen Staff"
        EVENT_MANAGER = "EVENT_MANAGER", "Event Manager"
        GYM_MANAGER = "GYM_MANAGER", "Gym Manager"
        GUEST = "GUEST", "Guest"

    role = models.CharField(max_length=50, choices=Role.choices, default=Role.GUEST)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    @property
    def can_manage_bookings(self):
        return self.role in [self.Role.ADMIN, self.Role.MANAGER, self.Role.RECEPTIONIST] or self.has_perm('booking.add_booking')

    @property
    def can_view_bookings(self):
        return self.can_manage_bookings or self.has_perm('booking.view_booking')

    @property
    def can_manage_rooms(self):
        return self.role in [self.Role.ADMIN, self.Role.MANAGER] or self.has_perm('hotel.change_room')

    @property
    def can_view_rooms(self):
        return self.role in [self.Role.ADMIN, self.Role.MANAGER, self.Role.RECEPTIONIST, self.Role.STAFF, self.Role.CLEANER] or self.has_perm('hotel.view_room')

    @property
    def can_manage_users(self):
        return self.role in [self.Role.ADMIN] or self.has_perm('accounts.change_user')

    @property
    def can_manage_staff(self):
        return self.role in [self.Role.ADMIN, self.Role.MANAGER] or self.has_perm('accounts.add_user')

    @property
    def can_manage_billing(self):
        return self.role in [self.Role.ADMIN, self.Role.MANAGER, self.Role.RECEPTIONIST] or self.has_perm('billing.view_invoice')

    @property
    def can_manage_settings(self):
        return self.role in [self.Role.ADMIN, self.Role.MANAGER] or self.has_perm('core.change_sitesetting')

    @property
    def can_manage_menu(self):
        return self.role in [self.Role.ADMIN, self.Role.MANAGER, self.Role.KITCHEN] or self.has_perm('services.add_menuitem')

    @property
    def can_manage_events(self):
        return self.role in [self.Role.ADMIN, self.Role.MANAGER, self.Role.EVENT_MANAGER] or self.has_perm('events.add_eventbooking')

    @property
    def can_manage_gym(self):
        return self.role in [self.Role.ADMIN, self.Role.MANAGER, self.Role.GYM_MANAGER] or self.has_perm('gym.add_gymmembership')
