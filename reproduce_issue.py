import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hms_core.settings')
django.setup()

from accounts.forms import RegistrationForm
from accounts.models import User

# Test data
data = {
    'username': 'testuser123',
    'email': 'testuser123@example.com',
    'first_name': 'Test',
    'last_name': 'User',
    'phone_number': '1234567890',
    'password': 'StrongPassword123!',
    'password_confirm': 'StrongPassword123!'
}

print("Attempting to create user with data:", data)

form = RegistrationForm(data=data)

if form.is_valid():
    print("Form is valid.")
    try:
        user = form.save()
        print(f"User created successfully: {user.username} (ID: {user.id})")
        
        # Verify password is set
        if user.check_password(data['password']):
            print("Password verification successful.")
        else:
            print("ERROR: Password verification failed!")
            
        # Clean up
        user.delete()
        print("Test user deleted.")
    except Exception as e:
        print(f"ERROR during save: {e}")
else:
    print("Form is INVALID.")
    print("Errors:", form.errors)
