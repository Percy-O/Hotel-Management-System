from django import forms
from billing.models import PaymentGateway

class PaymentGatewayForm(forms.ModelForm):
    class Meta:
        model = PaymentGateway
        fields = ['name', 'public_key', 'secret_key', 'is_active', 'is_test_mode']
        widgets = {
            'name': forms.Select(attrs={'class': 'w-full bg-surface-light dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg px-4 py-3'}),
            'public_key': forms.TextInput(attrs={'class': 'w-full bg-surface-light dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg px-4 py-3'}),
            'secret_key': forms.TextInput(attrs={'class': 'w-full bg-surface-light dark:bg-surface-dark border border-gray-300 dark:border-gray-700 rounded-lg px-4 py-3'}),
        }
