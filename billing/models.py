from django.db import models
from booking.models import Booking

class Invoice(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PAID = 'PAID', 'Paid'
        CANCELLED = 'CANCELLED', 'Cancelled'

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='invoices', null=True, blank=True)
    # Add new relations for Events and Gym
    event_booking = models.ForeignKey('events.EventBooking', on_delete=models.CASCADE, related_name='invoices', null=True, blank=True)
    gym_membership = models.ForeignKey('gym.GymMembership', on_delete=models.CASCADE, related_name='invoices', null=True, blank=True)
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    issued_date = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"Invoice {self.id} - {self.booking}"

class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'CASH', 'Cash'
        PAYSTACK = 'PAYSTACK', 'Paystack'
        FLUTTERWAVE = 'FLUTTERWAVE', 'Flutterwave'
        TRANSFER = 'TRANSFER', 'Bank Transfer'

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=Method.choices)
    transaction_id = models.CharField(max_length=100, blank=True)
    payment_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.id} - {self.amount}"

class PaymentGateway(models.Model):
    class Provider(models.TextChoices):
        PAYSTACK = 'PAYSTACK', 'Paystack'
        FLUTTERWAVE = 'FLUTTERWAVE', 'Flutterwave'

    name = models.CharField(max_length=20, choices=Provider.choices, unique=True)
    public_key = models.CharField(max_length=255)
    secret_key = models.CharField(max_length=255)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_name_display()} ({'Active' if self.is_active else 'Inactive'})"
