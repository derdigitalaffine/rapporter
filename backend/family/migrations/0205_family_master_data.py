import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("family", "0204_today_layout")]

    operations = [
        migrations.CreateModel(
            name="FamilyMasterData",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("image_key", models.CharField(blank=True, max_length=64)),
                ("image_version", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("address_street", models.CharField(blank=True, max_length=160)),
                ("address_house_number", models.CharField(blank=True, max_length=32)),
                ("address_postal_code", models.CharField(blank=True, max_length=32)),
                ("address_city", models.CharField(blank=True, max_length=120)),
                ("address_region", models.CharField(blank=True, max_length=120)),
                ("address_country_code", models.CharField(blank=True, max_length=2)),
                ("family", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="master_data", to="family.family")),
            ],
            options={"verbose_name": "family master data", "verbose_name_plural": "family master data"},
        )
    ]
