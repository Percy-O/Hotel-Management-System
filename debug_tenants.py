import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hms_core.settings')
django.setup()

from tenants.models import Domain, Tenant
print("--- DEBUG DOMAINS ---")
for d in Domain.objects.all():
    print(f"Domain: {d.domain} -> Tenant: {d.tenant.name}")

print("\n--- DEBUG TENANTS ---")
for t in Tenant.objects.all():
    print(f"Tenant: {t.name}, Subdomain: {t.subdomain}")
