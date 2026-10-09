import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0008_task_source_length"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationPreference",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tasks", models.BooleanField(default=True)),
                ("task_assigned", models.BooleanField(default=True)),
                ("shopping", models.BooleanField(default=True)),
                ("calendar", models.BooleanField(default=True)),
                ("family_updates", models.BooleanField(default=True)),
                ("messages", models.BooleanField(default=True)),
                ("routines", models.BooleanField(default=True)),
                ("membership", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="notification_preference", to="family.membership")),
            ],
        ),
        migrations.CreateModel(
            name="LoyaltyCard",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("logo", models.CharField(blank=True, max_length=120)),
                ("color", models.CharField(default="#6750A4", max_length=24)),
                ("holder_name", models.CharField(blank=True, max_length=120)),
                ("customer_number", models.CharField(blank=True, max_length=160)),
                ("barcode_value", models.TextField()),
                ("barcode_format", models.CharField(choices=[("code128", "Code 128"), ("ean13", "EAN-13"), ("ean8", "EAN-8"), ("upca", "UPC-A"), ("upce", "UPC-E"), ("code39", "Code 39"), ("itf", "Interleaved 2 of 5"), ("qrcode", "QR Code"), ("datamatrix", "Data Matrix"), ("pdf417", "PDF417"), ("aztec", "Aztec")], default="code128", max_length=24)),
                ("note", models.TextField(blank=True)),
                ("favorite", models.BooleanField(default=False)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("archived", models.BooleanField(default=False)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_loyalty_cards", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="loyalty_cards", to="family.family")),
                ("holder_membership", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="held_loyalty_cards", to="family.membership")),
                ("shared_with", models.ManyToManyField(blank=True, related_name="shared_loyalty_cards", to="family.membership")),
            ],
            options={"ordering": ["-favorite", "sort_order", "name"]},
        ),
    ]
