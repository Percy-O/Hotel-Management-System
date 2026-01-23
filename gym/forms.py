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

class PublicGymSignupForm(forms.ModelForm):
    email = forms.EmailField(required=True, label="Email Address")
    full_name = forms.CharField(required=True, label="Full Name")
    phone_number = forms.CharField(required=True, label="Phone Number")
    
    class Meta:
        model = GymMembership
        fields = ['plan', 'start_date', 'email', 'full_name', 'phone_number']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full p-4 bg-white/5 border border-white/10 text-white rounded-lg focus:outline-none focus:border-gold-500'}),
            'plan': forms.Select(attrs={'class': 'w-full p-4 bg-dark-800 border border-white/10 text-white rounded-lg focus:outline-none focus:border-gold-500'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        self.fields['email'].widget.attrs.update={'class': 'w-full p-4 bg-white/5 border border-white/10 text-white rounded-lg focus:outline-none focus:border-gold-500', 'placeholder': 'john@example.com'}
        self.fields['full_name'].widget.attrs.update={'class': 'w-full p-4 bg-white/5 border border-white/10 text-white rounded-lg focus:outline-none focus:border-gold-500', 'placeholder': 'John Doe'}
        self.fields['phone_number'].widget.attrs.update={'class': 'w-full p-4 bg-white/5 border border-white/10 text-white rounded-lg focus:outline-none focus:border-gold-500', 'placeholder': '+1 234 567 890'}

        if user and user.is_authenticated:
            self.fields['email'].initial = user.email
            self.fields['email'].widget.attrs['readonly'] = True
            self.fields['full_name'].initial = f"{user.first_name} {user.last_name}"
            self.fields['phone_number'].initial = getattr(user, 'phone_number', '')
