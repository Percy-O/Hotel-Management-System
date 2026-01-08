from django import forms
from core.models import SiteSetting

class HousekeepingSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = ['housekeeping_info']
        widgets = {
            'housekeeping_info': forms.Textarea(attrs={'rows': 6, 'placeholder': 'Enter housekeeping schedule, policies, and other important information for guests...'}),
        }
        labels = {
            'housekeeping_info': 'Housekeeping Policy & Information',
        }
