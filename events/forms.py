from django import forms
from .models import EventHall, EventBooking

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class EventHallForm(forms.ModelForm):
    # Explicitly define image to ensure it is not required
    image = forms.ImageField(
        label="Main Image",
        required=False,
        widget=forms.ClearableFileInput()
    )
    
    # Make price optional in form so we can default it to 0.00
    price = forms.DecimalField(max_digits=10, decimal_places=2, required=False, initial=0.00, widget=forms.NumberInput(attrs={'placeholder': '0.00'}))

    class Meta:
        model = EventHall
        fields = ['name', 'description', 'amenities', 'capacity', 'pricing_type', 'price', 'image', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Describe the event hall...'}),
            'amenities': forms.Textarea(attrs={'rows': 2, 'placeholder': 'WiFi, Projector, Sound System, Catering (Comma separated)'}),
        }
    
    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is None:
            return 0.00
        return price

class EventBookingForm(forms.ModelForm):
    class Meta:
        model = EventBooking
        fields = ['hall', 'event_name', 'start_time', 'end_time', 'notes']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        hall = cleaned_data.get('hall')

        if start_time and end_time:
            if start_time >= end_time:
                raise forms.ValidationError("End time must be after start time.")

            # Check for overlaps
            # Note: This simple check doesn't account for existing instance on update.
            # In a real view, we might need to exclude self.instance.pk
            overlaps = EventBooking.objects.filter(
                hall=hall,
                status__in=['CONFIRMED', 'PENDING'],
                start_time__lt=end_time,
                end_time__gt=start_time
            )
            if self.instance.pk:
                overlaps = overlaps.exclude(pk=self.instance.pk)
            
            if overlaps.exists():
                raise forms.ValidationError("This hall is already booked for the selected time slot.")
        
        return cleaned_data
