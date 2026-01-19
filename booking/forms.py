from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from .models import Booking

User = get_user_model()

class BookingForm(forms.ModelForm):
    first_name = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Booking
        fields = ['check_in_date', 'check_out_date', 'guest_name', 'guest_email', 'guest_phone', 'first_name', 'last_name']
        widgets = {
            'check_in_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'check_out_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'guest_name': forms.HiddenInput(), # We'll construct this from first/last name
            'guest_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'guest_phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        check_in = cleaned_data.get('check_in_date')
        check_out = cleaned_data.get('check_out_date')

        if check_in and check_out:
            if check_in < timezone.now():
                raise ValidationError("Check-in date cannot be in the past.")
            
            if check_out <= check_in:
                raise ValidationError("Check-out date must be after check-in date.")

        return cleaned_data

class AdminBookingForm(BookingForm):
    user = forms.ModelChoiceField(
        queryset=User.objects.none(), 
        required=False,
        label="Select Guest Account",
        help_text="Leave blank for walk-in guest"
    )
    
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('TRANSFER', 'Bank Transfer'),
        ('ONLINE', 'Online Payment (Paystack/Flutterwave)'),
    ]
    
    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'}),
        initial='CASH',
        label="Payment Method"
    )

    class Meta(BookingForm.Meta):
        fields = ['user', 'guest_name', 'guest_email', 'guest_phone', 'check_in_date', 'check_out_date', 'first_name', 'last_name', 'payment_method']

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if tenant:
            # Show users who have a membership with this tenant (Staff, Past Guests)
            self.fields['user'].queryset = User.objects.filter(memberships__tenant=tenant, is_active=True).distinct()
        else:
            self.fields['user'].queryset = User.objects.none()
