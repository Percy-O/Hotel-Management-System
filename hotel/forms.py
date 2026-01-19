from django import forms
from .models import Room, RoomType

class RoomTypeForm(forms.ModelForm):
    class Meta:
        model = RoomType
        fields = ['name', 'description', 'amenities', 'price_per_night', 'capacity', 'number_of_rooms', 'image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'resize-none', 'placeholder': 'Describe the room features and view...'}),
            'amenities': forms.Textarea(attrs={'rows': 3, 'placeholder': 'WiFi, King Bed, Ocean View, Breakfast (Comma separated)', 'class': 'resize-none'}),
        }

class BulkRoomForm(forms.Form):
    room_type = forms.ModelChoiceField(queryset=RoomType.objects.none(), empty_label="Select Room Type")
    starting_number = forms.IntegerField(min_value=1, initial=101, help_text="Starting room number (e.g., 101).")
    floor_prefix = forms.BooleanField(required=False, initial=True, help_text="Use first digit(s) as floor number?")

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['room_type'].queryset = RoomType.objects.filter(tenant=tenant)
        else:
            self.fields['room_type'].queryset = RoomType.objects.none()


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['room_type', 'room_number', 'floor', 'status']
        widgets = {
            'status': forms.Select(attrs={'class': 'cursor-pointer'}),
        }

    def __init__(self, *args, **kwargs):
        tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        if tenant:
             self.fields['room_type'].queryset = RoomType.objects.filter(tenant=tenant)
        else:
             self.fields['room_type'].queryset = RoomType.objects.none()
