from django import forms
from .models import Tenant, Domain

class TenantForm(forms.ModelForm):
    domain = forms.CharField(max_length=255, help_text="e.g. hotelname.localhost or hotelname.com")
    
    class Meta:
        model = Tenant
        fields = ['name', 'subdomain']

    def clean_domain(self):
        domain = self.cleaned_data['domain']
        if Domain.objects.filter(domain=domain).exists():
            raise forms.ValidationError("Domain already exists.")
        return domain

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'w-full bg-background-dark/50 border border-border-dark rounded-lg px-4 py-3 text-text-main focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            })
