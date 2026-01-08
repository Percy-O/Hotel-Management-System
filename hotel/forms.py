from django import forms
from .models import Room, RoomType

class RoomTypeForm(forms.ModelForm):
    class Meta:
        model = RoomType
        fields = ['name', 'description', 'amenities', 'price_per_night', 'capacity', 'number_of_rooms', 'image']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'resize-none'}),
            'amenities': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Wifi, Pool, Breakfast...', 'class': 'resize-none'}),
        }

class BulkRoomForm(forms.Form):
    room_type = forms.ModelChoiceField(queryset=RoomType.objects.all(), empty_label="Select Room Type")
    starting_number = forms.IntegerField(min_value=1, initial=101, help_text="Starting room number (e.g., 101).")
    floor_prefix = forms.BooleanField(required=False, initial=True, help_text="Use first digit(s) as floor number?")


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['room_type', 'room_number', 'floor', 'status']
        widgets = {
            'status': forms.Select(attrs={'class': 'cursor-pointer'}),
        }
