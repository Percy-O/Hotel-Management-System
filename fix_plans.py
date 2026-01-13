import os
import django
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hms_core.settings')
django.setup()

from tenants.models import Plan
from decimal import Decimal

def fix_plans():
    log_path = os.path.join(os.getcwd(), 'fix_plans_log.txt')
    with open(log_path, 'w') as f:
        try:
            f.write("Starting fix_plans...\n")
            
            # Check existing
            count = Plan.objects.count()
            f.write(f"Existing plans: {count}\n")
            
            if count == 0:
                f.write("Creating default plans...\n")
                
                Plan.objects.create(
                    name="Starter",
                    # slug="starter", # Not in model
                    # description="Perfect for small hotels", # Not in model
                    price=Decimal("0.00"),
                    is_public=True,
                    max_users=5,
                    max_rooms=10,
                    features="Basic Reporting, 10 Rooms, 5 Users",
                    # max_storage=1024
                )
                
                Plan.objects.create(
                    name="Professional",
                    # slug="professional", 
                    # description="For growing businesses",
                    price=Decimal("29000.00"), # NGN
                    is_public=True,
                    max_users=20,
                    max_rooms=50,
                    features="Advanced Reporting, 50 Rooms, 20 Users, Event Module",
                    module_events=True,
                    # max_storage=10240
                )
                
                Plan.objects.create(
                    name="Enterprise",
                    # slug="enterprise",
                    # description="For large chains",
                    price=Decimal("99000.00"),
                    is_public=True,
                    max_users=100,
                    max_rooms=200,
                    features="Full Suite, 200 Rooms, 100 Users, All Modules",
                    module_events=True,
                    module_gym=True,
                    module_restaurant=True,
                    # max_storage=102400
                )
                f.write("Created 3 plans.\n")
            else:
                # Ensure all are public
                updated = Plan.objects.update(is_public=True)
                f.write(f"Updated {updated} plans to be public.\n")
                
            # Verify
            final_count = Plan.objects.filter(is_public=True).count()
            f.write(f"Final public plans count: {final_count}\n")
            
        except Exception as e:
            f.write(f"Error: {str(e)}\n")

if __name__ == "__main__":
    fix_plans()
