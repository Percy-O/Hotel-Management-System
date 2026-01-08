from django.db import models

class Hotel(models.Model):
    name = models.CharField(max_length=255)
    address = models.TextField()
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='hotels/', blank=True, null=True)

    def __str__(self):
        return self.name

class RoomType(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='room_types')
    name = models.CharField(max_length=100) # e.g. Deluxe, Suite
    description = models.TextField(blank=True)
    amenities = models.TextField(blank=True, help_text="Comma-separated list of amenities")
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.IntegerField()
    number_of_rooms = models.PositiveIntegerField(default=1, help_text="Total number of rooms for this category")
    # Main cover image (kept for backward compatibility and list views)
    image = models.ImageField(upload_to='room_types/', blank=True, null=True)

    def __str__(self):
        return f"{self.name} - {self.hotel.name}"

class RoomImage(models.Model):
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='room_types/gallery/')
    caption = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.room_type.name}"

class Review(models.Model):
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='reviews')
    guest_name = models.CharField(max_length=100)
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.guest_name} - {self.room_type.name} ({self.rating} stars)"

class Room(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        OCCUPIED = 'OCCUPIED', 'Occupied'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'
        CLEANING = 'CLEANING', 'Cleaning'

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='rooms')
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='rooms')
    room_number = models.CharField(max_length=10)
    floor = models.CharField(max_length=10, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    
    def __str__(self):
        return f"{self.room_id} ({self.room_type.name})"

    @property
    def room_id(self):
        return f"RM-{self.room_number}"