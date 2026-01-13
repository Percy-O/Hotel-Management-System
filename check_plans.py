import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hms_core.settings')
django.setup()

from tenants.models import Plan

def check_plans():
    with open('plans_log.txt', 'w') as f:
        f.write("Checking plans...\n")
        plans = Plan.objects.all()
        f.write(f"Total plans: {plans.count()}\n")
        for plan in plans:
            f.write(f"Plan: {plan.name}, Public: {plan.is_public}, Price: {plan.price}\n")

        public_plans = Plan.objects.filter(is_public=True)
        f.write(f"Public plans query count: {public_plans.count()}\n")

if __name__ == "__main__":
    check_plans()
