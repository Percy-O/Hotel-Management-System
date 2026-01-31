from django.db import models
from accounts.models import User

class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Create'
        UPDATE = 'UPDATE', 'Update'
        DELETE = 'DELETE', 'Delete'
        LOGIN = 'LOGIN', 'Login'
        LOGOUT = 'LOGOUT', 'Logout'
        PAYMENT = 'PAYMENT', 'Payment'
        OTHER = 'OTHER', 'Other'

    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='audit_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='audit_logs', null=True, blank=True)
    action = models.CharField(max_length=20, choices=Action.choices, default=Action.OTHER)
    module = models.CharField(max_length=50, help_text="Module/App name (e.g. Booking, Billing)")
    details = models.TextField(help_text="Description of the action")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.timestamp}] {self.user} - {self.action} ({self.module})"

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
    custom_primary_color = models.CharField(max_length=7, default='#13ec6d', help_text="Hex code for primary color", blank=True)
    custom_secondary_color = models.CharField(max_length=7, default='#1e293b', help_text="Hex code for secondary color", blank=True)
    custom_accent_color = models.CharField(max_length=7, default='#f59e0b', help_text="Hex code for accent color (Gold/Yellow)", blank=True)
    
    custom_background_color = models.CharField(max_length=7, default='#0f172a', help_text="Hex code for background color", blank=True)
    custom_surface_color = models.CharField(max_length=7, default='#1e293b', help_text="Hex code for surface/card color", blank=True)
    custom_card_background_color = models.CharField(max_length=7, default='#0f172a', help_text="Hex code for listing cards (Rooms, Halls, Plans)", blank=True)
    custom_section_background_color = models.CharField(max_length=7, default='#0f172a', help_text="Hex code for page sections", blank=True)
    custom_text_color = models.CharField(max_length=7, default='#ffffff', help_text="Hex code for main text color", blank=True)
    
    custom_button_color = models.CharField(max_length=7, default='#f59e0b', help_text="Hex code for button background color", blank=True)
    custom_button_text_color = models.CharField(max_length=7, default='#ffffff', help_text="Hex code for button text color", blank=True)
    
    # Hotel Identity
    hotel_name = models.CharField(max_length=255, default="My Hotel", blank=True)
    hotel_tagline = models.CharField(max_length=255, default="Luxury Stay", blank=True, help_text="A short tagline shown below the hotel name")
    hotel_description = models.TextField(blank=True, default="Experience a world of comfort and elegance in the heart of the city. Your perfect gateway begins here.", help_text="Short description for the footer")
    hotel_logo = models.ImageField(upload_to='site/', blank=True, null=True)
    booking_id_prefix = models.CharField(max_length=10, default="HMS", blank=True, help_text="Prefix for booking IDs (e.g., HMS -> HMS-2024-0001)")

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
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='NGN', blank=True)
    
    # Contact Info
    contact_email = models.EmailField(default="info@example.com", blank=True)
    contact_phone = models.CharField(max_length=50, default="+1 234 567 8900", blank=True)
    address = models.TextField(default="123 Luxury Ave, City", blank=True)
    
    # Hero Section
    hero_title = models.CharField(max_length=255, default="Experience Luxury", blank=True)
    hero_subtitle = models.CharField(max_length=255, default="Discover comfort, elegance, and unforgettable moments.", blank=True)
    hero_background = models.ImageField(upload_to='site/hero/', blank=True, null=True, help_text="Main hero background image")
    hero_cta_text = models.CharField(max_length=50, default="Book Now", blank=True)
    hero_cta_link = models.CharField(max_length=255, default="#rooms", blank=True)

    # Pages Content
    faq_content = models.TextField(blank=True, default="No FAQs available yet.", help_text="HTML content for FAQs page")
    privacy_policy = models.TextField(blank=True, default="Privacy Policy content goes here.", help_text="HTML content for Privacy Policy page")
    terms_conditions = models.TextField(blank=True, default="Terms and Conditions content goes here.", help_text="HTML content for Terms & Conditions page")
    about_us_content = models.TextField(blank=True, default="""<h2 class="text-3xl font-bold text-text-main">Our Story</h2>
<p class="text-text-secondary-dark leading-relaxed">
    Founded with a vision to redefine hospitality, our hotel stands as a beacon of elegance and service. 
    Every corner of our hotel is designed with your comfort in mind, blending contemporary aesthetics with timeless charm.
</p>
<p class="text-text-secondary-dark leading-relaxed">
    Whether you are here for business or leisure, our dedicated team is committed to ensuring your stay is nothing short of perfection.
</p>""", help_text="HTML content for About Us page (Our Story section)")
    
    why_choose_us_content = models.TextField(blank=True, default="""<div class="grid grid-cols-1 md:grid-cols-3 gap-8">
    <div class="text-center space-y-4">
        <div class="size-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto text-primary">
            <span class="material-symbols-outlined text-3xl">diamond</span>
        </div>
        <h3 class="text-xl font-bold text-text-main">Premium Comfort</h3>
        <p class="text-text-secondary-dark text-sm">Experience the pinnacle of luxury with our carefully curated amenities and spaces.</p>
    </div>
    <div class="text-center space-y-4">
        <div class="size-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto text-primary">
            <span class="material-symbols-outlined text-3xl">restaurant</span>
        </div>
        <h3 class="text-xl font-bold text-text-main">Exquisite Dining</h3>
        <p class="text-text-secondary-dark text-sm">Savor culinary masterpieces prepared by our world-class chefs.</p>
    </div>
    <div class="text-center space-y-4">
        <div class="size-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto text-primary">
            <span class="material-symbols-outlined text-3xl">spa</span>
        </div>
        <h3 class="text-xl font-bold text-text-main">Relaxation</h3>
        <p class="text-text-secondary-dark text-sm">Unwind and rejuvenate in our state-of-the-art wellness centers.</p>
    </div>
</div>""", help_text="HTML content for Why Choose Us section")

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
    email_port = models.IntegerField(default=587, help_text="SMTP Port (e.g., 587 or 465)", blank=True, null=True)
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
        return symbols.get(self.currency, '₦')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"Settings for {self.tenant}"

class ContactMessage(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='contact_messages', null=True)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    subject = models.CharField(max_length=255, default="General Inquiry")
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message from {self.name} - {self.subject}"

class HotelFacility(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='facilities')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, help_text="Short description of the facility")
    icon = models.CharField(max_length=50, blank=True, help_text="Material Symbol name (e.g. wifi, pool, spa)")
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0, help_text="Display order")

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = "Hotel Facilities"

    def save(self, *args, **kwargs):
        # Auto-assign icon if empty
        if not self.icon and self.name:
            name_lower = self.name.lower()
            if 'wifi' in name_lower or 'internet' in name_lower:
                self.icon = 'wifi'
            elif 'pool' in name_lower or 'swim' in name_lower:
                self.icon = 'pool'
            elif 'gym' in name_lower or 'fitness' in name_lower or 'workout' in name_lower:
                self.icon = 'fitness_center'
            elif 'spa' in name_lower or 'massage' in name_lower or 'sauna' in name_lower:
                self.icon = 'spa'
            elif 'restaurant' in name_lower or 'dining' in name_lower or 'food' in name_lower:
                self.icon = 'restaurant'
            elif 'bar' in name_lower or 'drink' in name_lower or 'cocktail' in name_lower:
                self.icon = 'local_bar'
            elif 'parking' in name_lower or 'car' in name_lower:
                self.icon = 'local_parking'
            elif 'laundry' in name_lower or 'cleaning' in name_lower:
                self.icon = 'local_laundry_service'
            elif 'room service' in name_lower:
                self.icon = 'room_service'
            elif 'ac' in name_lower or 'air condition' in name_lower:
                self.icon = 'ac_unit'
            elif 'tv' in name_lower or 'television' in name_lower:
                self.icon = 'tv'
            elif 'conference' in name_lower or 'meeting' in name_lower:
                self.icon = 'meeting_room'
            elif 'concierge' in name_lower:
                self.icon = 'concierge'
            elif 'airport' in name_lower or 'shuttle' in name_lower:
                self.icon = 'airport_shuttle'
            elif 'beach' in name_lower:
                self.icon = 'beach_access'
            elif 'security' in name_lower:
                self.icon = 'security'
            elif 'elevator' in name_lower or 'lift' in name_lower:
                self.icon = 'elevator'
            elif 'garden' in name_lower:
                self.icon = 'yard'
            else:
                self.icon = 'hotel' # Default
        
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class GlobalSetting(models.Model):
    # SMTP Settings
    email_host = models.CharField(max_length=255, default='mail.techohr.com.ng')
    email_port = models.IntegerField(default=465)
    email_host_user = models.CharField(max_length=255, default='spaxce@techohr.com.ng')
    email_host_password = models.CharField(max_length=255, blank=True)
    email_use_tls = models.BooleanField(default=False)
    email_use_ssl = models.BooleanField(default=True)
    default_from_email = models.EmailField(default='spaxce@techohr.com.ng')

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
