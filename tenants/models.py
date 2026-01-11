from django.db import models
from django.conf import settings
from django.utils.text import slugify

class Plan(models.Model):
    name = models.CharField(max_length=50) # Free, Basic, Premium
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    max_rooms = models.PositiveIntegerField(default=5)
    max_users = models.PositiveIntegerField(default=2)
    features = models.TextField(blank=True, help_text="Comma separated list of features")
    is_public = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.name} ({self.max_rooms} Rooms)"

class Tenant(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    subdomain = models.CharField(max_length=100, unique=True, blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_tenants')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Branding
    logo = models.ImageField(upload_to='tenant_logos/', blank=True, null=True)
    primary_color = models.CharField(max_length=7, default='#3b82f6')
    
    # Subscription/Plan info
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name='tenants')
    is_active = models.BooleanField(default=True)
    subscription_id = models.CharField(max_length=100, blank=True, null=True)
    subscription_status = models.CharField(max_length=50, default='active') # active, past_due, canceled
    subscription_end_date = models.DateTimeField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Domain(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='domains')
    domain = models.CharField(max_length=255, unique=True)
    is_primary = models.BooleanField(default=True)

    def __str__(self):
        return self.domain

class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=50, blank=True, help_text="Role within this specific tenant")
    date_joined = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'tenant')
    
    def __str__(self):
        return f"{self.user} in {self.tenant}"

class TenantAwareModel(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)

    class Meta:
        abstract = True
