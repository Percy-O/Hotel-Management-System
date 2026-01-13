from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import User

class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(), required=True, help_text="Enter a strong password")
    password_confirm = forms.CharField(widget=forms.PasswordInput(), required=True, label="Confirm Password")

    class Meta:
        model = User
        fields = ('username', 'email')

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', "Passwords do not match")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['username']
        user.email = self.cleaned_data['email']
        
        if self.cleaned_data.get('password'):
            user.set_password(self.cleaned_data['password'])
            
        if commit:
            user.save()
        return user

class HotelSignupForm(RegistrationForm):
    hotel_name = forms.CharField(max_length=100, required=True, label="Hotel Name")
    subdomain = forms.CharField(max_length=100, required=False, label="Hotel Subdomain", help_text="Leave blank to generate from hotel name")
    billing_cycle = forms.ChoiceField(choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')], required=True, widget=forms.RadioSelect, initial='monthly')

    class Meta(RegistrationForm.Meta):
        fields = RegistrationForm.Meta.fields + ('hotel_name', 'subdomain', 'billing_cycle')

    def clean_subdomain(self):
        subdomain = self.cleaned_data.get('subdomain')
        if subdomain:
             # Basic validation (alphanumeric only, but allow hyphens)
             # if not subdomain.isalnum(): 
             #    raise forms.ValidationError("Subdomain must be alphanumeric")
             
             # Check availability (needs model import inside method to avoid circular imports if in same file, but here models are available)
             from tenants.models import Tenant
             if Tenant.objects.filter(subdomain=subdomain).exists():
                 raise forms.ValidationError("This subdomain is already taken.")
        return subdomain

class LoginForm(AuthenticationForm):
    pass

class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(), required=False, help_text="Leave empty to keep current password")
    confirm_password = forms.CharField(widget=forms.PasswordInput(), required=False, label="Confirm Password")
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'first_name', 'last_name', 'phone_number', 'role')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            if self.user.role == User.Role.MANAGER:
                # Managers can only assign certain roles
                allowed_roles = [
                    (User.Role.RECEPTIONIST, 'Receptionist'),
                    (User.Role.STAFF, 'Staff'),
                    (User.Role.CLEANER, 'Cleaner'),
                    (User.Role.GUEST, 'Guest'),
                ]
                self.fields['role'].choices = allowed_roles
            elif self.user.role == User.Role.ADMIN:
                # Admins can assign all roles
                pass # Default choices are fine
            else:
                # Others shouldn't be creating users usually, but if so, restrict to Guest?
                self.fields['role'].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match")
            
        # For new users, password is required
        if not self.instance.pk and not password:
            self.add_error('password', "Password is required for new users")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            # Save many-to-many data (permissions)
            self.save_m2m()
        return user
