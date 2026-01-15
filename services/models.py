from django.db import models
from django.conf import settings
from booking.models import Booking
from billing.models import Invoice

class MenuItem(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='menu_items', null=True, blank=True)
    CATEGORY_CHOICES = [
        ('FOOD', 'Food'),
        ('DRINK', 'Drink'),
        ('OTHER', 'Other'),
    ]
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='FOOD')
    image = models.ImageField(upload_to='menu_items/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (${self.price})"

class GuestOrder(models.Model):
    STATUS_CHOICES = [
        ('AWAITING_PAYMENT', 'Awaiting Payment'),
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='guest_orders')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    assigned_staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_orders')
    room_number = models.CharField(max_length=10, blank=True, help_text="Room number for delivery")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    note = models.TextField(blank=True, help_text="Special requests or allergies")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_total(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_price = total
        self.save()

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"

class OrderItem(models.Model):
    order = models.ForeignKey(GuestOrder, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    
    @property
    def subtotal(self):
        return self.menu_item.price * self.quantity

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name}"

class HousekeepingServiceType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='cleaning_services', help_text="Material Symbol icon name")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class HousekeepingRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # Deprecated: Kept for historical data
    TYPE_CHOICES = [
        ('CLEANING', 'Room Cleaning'),
        ('TOWELS', 'Extra Towels'),
        ('TOILETRIES', 'Toiletries'),
        ('MAINTENANCE', 'Maintenance Issue'),
        ('OTHER', 'Other'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='housekeeping_requests')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='housekeeping_requests')
    room_number = models.CharField(max_length=10, blank=True)
    
    # New Dynamic Type
    service_type = models.ForeignKey(HousekeepingServiceType, on_delete=models.SET_NULL, null=True, blank=True, related_name='requests')
    
    # Old field (make optional)
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='CLEANING', blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    note = models.TextField(blank=True)
    assigned_staff = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_housekeeping')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        type_name = self.service_type.name if self.service_type else self.get_request_type_display()
        return f"{type_name} - Room {self.room_number}"
