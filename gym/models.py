from django.db import models
from django.conf import settings
from decimal import Decimal

class GymPlan(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='gym_plans', null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.PositiveIntegerField(help_text="Duration of membership in days")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.duration_days} Days"

class GymMembership(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
        ('PENDING', 'Pending Payment'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gym_memberships')
    plan = models.ForeignKey(GymPlan, on_delete=models.SET_NULL, null=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    payment_status = models.CharField(max_length=20, default='PENDING') # Should link to Invoice ideally
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.plan.name if self.plan else 'Unknown Plan'}"

    @property
    def remaining_days(self):
        from django.utils import timezone
        if self.status != 'ACTIVE' or not self.end_date:
            return 0
        today = timezone.now().date()
        delta = (self.end_date - today).days
        return max(0, delta)

class GymAttendance(models.Model):
    membership = models.ForeignKey(GymMembership, on_delete=models.CASCADE, related_name='attendance_records')
    check_in = models.DateTimeField(auto_now_add=True)
    check_out = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.membership.user.username} - {self.check_in}"
