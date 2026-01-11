import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hms_core.settings')
django.setup()

from django.contrib.auth import get_user_model
from tenants.models import Tenant, Domain, Membership, Plan

User = get_user_model()

def setup():
    # Create Plans
    free_plan, _ = Plan.objects.get_or_create(
        name="Free Tier",
        defaults={
            'max_rooms': 5,
            'max_users': 2,
            'price': 0.00,
            'features': "Basic Dashboard, 5 Rooms Limit"
        }
    )
    basic_plan, _ = Plan.objects.get_or_create(
        name="Basic Plan",
        defaults={
            'max_rooms': 20,
            'max_users': 5,
            'price': 29.99,
            'features': "Advanced Dashboard, 20 Rooms, Email Support"
        }
    )
    premium_plan, _ = Plan.objects.get_or_create(
        name="Premium Plan",
        defaults={
            'max_rooms': 100,
            'max_users': 20,
            'price': 99.99,
            'features': "Unlimited Features, Priority Support"
        }
    )
    print("Plans created.")

    # Create Superuser
    if not User.objects.filter(username='admin').exists():
        admin = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
        print("Superuser 'admin' created.")
    else:
        admin = User.objects.get(username='admin')

    # Create Tenant
    tenant, created = Tenant.objects.get_or_create(
        name="Grand Hotel",
        defaults={
            'slug': 'grand-hotel', 
            'owner': admin, 
            'subdomain': 'grand',
            'plan': premium_plan # Assign premium to default tenant
        }
    )
    if not created:
        tenant.plan = premium_plan
        tenant.save()
        
    if created:
        print(f"Tenant '{tenant.name}' created.")
    else:
        print(f"Tenant '{tenant.name}' already exists.")

    # Create Domain
    # Map localhost to this tenant for easy access
    domain, created = Domain.objects.get_or_create(
        domain='localhost',
        defaults={'tenant': tenant, 'is_primary': True}
    )
    if created:
        print(f"Domain '{domain.domain}' created for tenant '{tenant.name}'.")
    
    # Also add 127.0.0.1 just in case
    Domain.objects.get_or_create(domain='127.0.0.1', tenant=tenant)

    # Add Membership
    Membership.objects.get_or_create(user=admin, tenant=tenant, role='ADMIN')
    print("Admin membership created.")

if __name__ == '__main__':
    setup()
