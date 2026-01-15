from django import forms
from .models import TenantSetting, GlobalSetting

class SiteSettingForm(forms.ModelForm):
    class Meta:
        model = TenantSetting
        fields = [
            'theme', 'custom_primary_color', 'custom_background_color', 'custom_surface_color',
            'hotel_name', 'hotel_tagline', 'hotel_description', 'hotel_logo', 'booking_id_prefix', 'currency', 
            'hero_title', 'hero_subtitle', 'hero_background', 'hero_cta_text', 'hero_cta_link',
            'contact_email', 'contact_phone', 'address', 
            'faq_content', 'privacy_policy', 'terms_conditions',
            'facebook_url', 'twitter_url', 'instagram_url',
            'enable_events', 'enable_gym',
            'email_host', 'email_port', 'email_host_user', 'email_host_password',
            'email_use_tls', 'email_use_ssl', 'default_from_email'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'hotel_description': forms.Textarea(attrs={'rows': 3}),
            'faq_content': forms.Textarea(attrs={'rows': 10, 'class': 'wysiwyg-editor'}),
            'privacy_policy': forms.Textarea(attrs={'rows': 10, 'class': 'wysiwyg-editor'}),
            'terms_conditions': forms.Textarea(attrs={'rows': 10, 'class': 'wysiwyg-editor'}),
            'custom_primary_color': forms.TextInput(attrs={'type': 'color'}),
            'custom_background_color': forms.TextInput(attrs={'type': 'color'}),
            'custom_surface_color': forms.TextInput(attrs={'type': 'color'}),
            'email_host_password': forms.PasswordInput(render_value=True),
        }

class GlobalSettingForm(forms.ModelForm):
    class Meta:
        model = GlobalSetting
        fields = [
            'email_host', 'email_port', 'email_host_user', 'email_host_password',
            'email_use_tls', 'email_use_ssl', 'default_from_email'
        ]
        widgets = {
            'email_host_password': forms.PasswordInput(render_value=True),
        }
