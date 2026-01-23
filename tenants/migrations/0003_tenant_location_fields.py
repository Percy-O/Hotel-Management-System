from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0002_tenant_payment_auth_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="address",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="tenant",
            name="city",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="tenant",
            name="state",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="tenant",
            name="country",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
