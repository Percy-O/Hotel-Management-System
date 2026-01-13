from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0003_tenant_auto_renew'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='billing_cycle',
            field=models.CharField(choices=[('monthly', 'Monthly'), ('yearly', 'Yearly')], default='monthly', max_length=10),
        ),
    ]
