from django import forms
from .models import TenantSetting

class SiteSettingForm(forms.ModelForm):
    class Meta:
        model = TenantSetting
        fields = [
            'theme', 'custom_primary_color', 'custom_background_color', 'custom_surface_color',
            'hotel_name', 'hotel_logo', 'currency', 
            'contact_email', 'contact_phone', 'address', 
            'facebook_url', 'twitter_url', 'instagram_url',
            'enable_events', 'enable_gym'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'custom_primary_color': forms.TextInput(attrs={'type': 'color'}),
            'custom_background_color': forms.TextInput(attrs={'type': 'color'}),
            'custom_surface_color': forms.TextInput(attrs={'type': 'color'}),
        }
