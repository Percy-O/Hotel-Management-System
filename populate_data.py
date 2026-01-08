import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hms_core.settings')
django.setup()

from hotel.models import Hotel, RoomType, Room

def create_initial_data():
    # Create Hotel
    hotel, created = Hotel.objects.get_or_create(
        name="Grand Plaza Hotel",
        defaults={
            "address": "123 Luxury Ave, Metropolis",
            "email": "info@grandplaza.com",
            "phone": "+1 234 567 8900",
            "description": "A 5-star experience in the heart of the city."
        }
    )
    
    if created:
        print(f"Created Hotel: {hotel.name}")
    else:
        print(f"Hotel {hotel.name} already exists")

    # Create Room Types
    types = [
        {
            "name": "Standard Room",
            "description": "A comfortable room with all basic amenities.",
            "price": Decimal("150.00"),
            "capacity": 2
        },
        {
            "name": "Deluxe Suite",
            "description": "Spacious suite with city views and premium amenities.",
            "price": Decimal("300.00"),
            "capacity": 3
        },
        {
            "name": "Presidential Suite",
            "description": "The ultimate luxury experience.",
            "price": Decimal("1000.00"),
            "capacity": 4
        }
    ]

    for t in types:
        rt, created = RoomType.objects.get_or_create(
            hotel=hotel,
            name=t["name"],
            defaults={
                "description": t["description"],
                "price_per_night": t["price"],
                "capacity": t["capacity"]
            }
        )
        if created:
            print(f"Created Room Type: {rt.name}")

            # Create Rooms for this type
            for i in range(1, 6):
                room_num = f"{rt.name[0]}{100+i}"
                Room.objects.get_or_create(
                    hotel=hotel,
                    room_type=rt,
                    room_number=room_num,
                    defaults={
                        "floor": "1",
                        "status": Room.Status.AVAILABLE
                    }
                )
            print(f"Created 5 rooms for {rt.name}")

if __name__ == "__main__":
    create_initial_data()
