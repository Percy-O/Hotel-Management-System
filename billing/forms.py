from django import forms
from .models import Payment

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'payment_method']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'w-full rounded-lg bg-background-dark border-border-dark text-text-main p-2.5', 'readonly': 'readonly'}),
            'payment_method': forms.Select(attrs={'class': 'w-full rounded-lg bg-background-dark border-border-dark text-text-main p-2.5'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['amount'].widget.attrs['readonly'] = True
        
        # Filter Payment Methods based on User Role
        if user:
            if not user.is_staff and not user.is_superuser:
                # Guests: Only Online Options
                allowed_methods = [
                    (Payment.Method.PAYSTACK, 'Paystack'),
                    (Payment.Method.FLUTTERWAVE, 'Flutterwave'),
                ]
                self.fields['payment_method'].choices = allowed_methods
            else:
                # Admin/Staff: All Options
                self.fields['payment_method'].choices = Payment.Method.choices
