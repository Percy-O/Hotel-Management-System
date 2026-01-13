from django.db import models
from accounts.models import User

class Notification(models.Model):
    class Type(models.TextChoices):
        INFO = 'INFO', 'Info'
        SUCCESS = 'SUCCESS', 'Success'
        WARNING = 'WARNING', 'Warning'
        ERROR = 'ERROR', 'Error'

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='notifications', null=True)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    # If null, it's a broadcast to all staff/admins
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=Type.choices, default=Type.INFO)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=255, blank=True, null=True) # Optional link to resource

    def __str__(self):
        return f"{self.title} - {self.recipient}"

class TenantSetting(models.Model):
    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE, related_name='settings', null=True)
    THEME_CHOICES = [
        ('theme-default', 'Default Dark'),
        ('theme-light', 'Light Mode'),
        ('theme-blue', 'Blue Horizon'),
        ('theme-luxury', 'Gold Luxury'),
        ('theme-forest', 'Forest Green'),
        ('theme-ocean', 'Ocean Breeze'),
        ('theme-sunset', 'Sunset Vibes'),
        ('theme-royal', 'Royal Purple'),
        ('theme-minimal', 'Minimalist Mono'),
        # New Themes
        ('theme-rose', 'Rose Garden'),
        ('theme-coffee', 'Coffee Break'),
        ('theme-lavender', 'Lavender Mist'),
        ('theme-midnight', 'Midnight Run'),
        ('theme-neon', 'Neon Cyberpunk'),
        ('theme-retro', 'Retro Wave'),
        ('theme-cherry', 'Cherry Blossom'),
        ('theme-dracula', 'Dracula Dark'),
        ('theme-corporate', 'Corporate Professional'),
        ('theme-custom', 'Custom Theme'),
    ]
    theme = models.CharField(max_length=50, choices=THEME_CHOICES, default='theme-default')
    
    # Custom Theme Fields
    custom_primary_color = models.CharField(max_length=7, default='#13ec6d', help_text="Hex code for primary color")
    custom_background_color = models.CharField(max_length=7, default='#0f172a', help_text="Hex code for background color")
    custom_surface_color = models.CharField(max_length=7, default='#1e293b', help_text="Hex code for surface/card color")
    
    # Hotel Identity
    hotel_name = models.CharField(max_length=255, default="My Hotel")
    hotel_logo = models.ImageField(upload_to='site/', blank=True, null=True)

    # Currency Settings
    CURRENCY_CHOICES = [
        ('USD', 'USD ($)'),
        ('EUR', 'EUR (€)'),
        ('GBP', 'GBP (£)'),
        ('NGN', 'NGN (₦)'),
        ('JPY', 'JPY (¥)'),
        ('CAD', 'CAD ($)'),
        ('AUD', 'AUD ($)'),
        ('INR', 'INR (₹)'),
        ('ZAR', 'ZAR (R)'),
    ]
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='USD')
    
    # Contact Info
    contact_email = models.EmailField(default="info@example.com")
    contact_phone = models.CharField(max_length=50, default="+1 234 567 8900")
    address = models.TextField(default="123 Luxury Ave, City")
    
    # Housekeeping Information
    housekeeping_info = models.TextField(blank=True, default="Standard housekeeping is available from 9:00 AM to 5:00 PM daily. Please request special services at least 2 hours in advance.", help_text="Information about cleaning schedules and policies.")

    # Social Media
    facebook_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)

    # Feature Toggles
    enable_events = models.BooleanField(default=False, help_text="Enable Events Management module (Halls, Bookings)")
    enable_gym = models.BooleanField(default=False, help_text="Enable Gym & Fitness module (Memberships, Access)")
    
    # Email Settings (Premium Only)
    email_host = models.CharField(max_length=255, blank=True, help_text="SMTP Server (e.g., smtp.gmail.com)")
    email_port = models.IntegerField(default=587, help_text="SMTP Port (e.g., 587 or 465)")
    email_host_user = models.CharField(max_length=255, blank=True, help_text="Email Address")
    email_host_password = models.CharField(max_length=255, blank=True, help_text="Email Password")
    email_use_tls = models.BooleanField(default=True, help_text="Use TLS (usually for port 587)")
    email_use_ssl = models.BooleanField(default=False, help_text="Use SSL (usually for port 465)")
    default_from_email = models.EmailField(blank=True, help_text="Default Sender Email")

    @property
    def currency_symbol(self):
        symbols = {
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'NGN': '₦',
            'JPY': '¥',
            'CAD': '$',
            'AUD': '$',
            'INR': '₹',
            'ZAR': 'R',
        }
        return symbols.get(self.currency, '$')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"Settings for {self.tenant}"

class GlobalSetting(models.Model):
    # SMTP Settings
    email_host = models.CharField(max_length=255, default='mail.techohr.com.ng')
    email_port = models.IntegerField(default=465)
    email_host_user = models.CharField(max_length=255, default='ihotel@techohr.com.ng')
    email_host_password = models.CharField(max_length=255, blank=True)
    email_use_tls = models.BooleanField(default=False)
    email_use_ssl = models.BooleanField(default=True)
    default_from_email = models.EmailField(default='ihotel@techohr.com.ng')

    def __str__(self):
        return "Global Site Settings"

    def save(self, *args, **kwargs):
        if not self.pk and GlobalSetting.objects.exists():
            # If you're trying to create a new one but one exists, just update the existing one?
            # Or prevent creation. For simplicity, we assume one instance.
            return GlobalSetting.objects.first()
        return super(GlobalSetting, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
