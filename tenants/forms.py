from django import forms
from .models import Tenant, Plan

class TenantForm(forms.ModelForm):
    domain = forms.CharField(max_length=255, required=False, help_text="Custom Domain (e.g. hotel.com) - Premium Only")
    
    class Meta:
        model = Tenant
        fields = ['name', 'billing_cycle']
        widgets = {
             'billing_cycle': forms.Select(attrs={'class': 'w-full bg-[#1e293b] border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-blue-500'})
        }

    def clean_domain(self):
        # ... existing logic ...
        return self.cleaned_data['domain']

class TenantSettingsForm(forms.ModelForm):
    custom_domain = forms.CharField(max_length=255, required=False, help_text="Your Custom Domain (e.g. hotel.com)")

    class Meta:
        model = Tenant
        fields = ['name', 'logo', 'primary_color', 'secondary_color', 'font_family', 'auto_renew']

    def clean_custom_domain(self):
        domain = self.cleaned_data.get('custom_domain')
        if domain:
            domain = domain.lower().strip()
            domain = domain.replace('http://', '').replace('https://', '').replace('www.', '')
            # Basic validation
            if '.' not in domain:
                 raise forms.ValidationError("Please enter a valid domain name (e.g., myhotel.com)")
        return domain


class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        fields = '__all__'
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full bg-surface-light dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg px-4 py-2'}),
            'price': forms.NumberInput(attrs={'class': 'w-full bg-surface-light dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg px-4 py-2'}),
            'max_rooms': forms.NumberInput(attrs={'class': 'w-full bg-surface-light dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg px-4 py-2'}),
            'max_users': forms.NumberInput(attrs={'class': 'w-full bg-surface-light dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg px-4 py-2'}),
            'features': forms.Textarea(attrs={'class': 'w-full bg-surface-light dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg px-4 py-2', 'rows': 3}),
        }
