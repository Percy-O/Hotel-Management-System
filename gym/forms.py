from django import forms
from .models import GymPlan, GymMembership

class GymPlanForm(forms.ModelForm):
    class Meta:
        model = GymPlan
        fields = ['name', 'description', 'price', 'duration_days', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

class GymMembershipForm(forms.ModelForm):
    class Meta:
        model = GymMembership
        fields = ['plan', 'start_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
        }
