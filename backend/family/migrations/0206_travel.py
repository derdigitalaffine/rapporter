import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0205_family_master_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Trip",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=160)),
                ("destination", models.CharField(blank=True, max_length=160)),
                ("starts_on", models.DateField()),
                ("ends_on", models.DateField()),
                ("notes", models.TextField(blank=True, max_length=10000)),
                ("archived", models.BooleanField(default=False)),
                ("calendar_event", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="travel_trip", to="family.familyevent")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_family_trips", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="trips", to="family.family")),
            ],
            options={"ordering": ["archived", "starts_on", "created_at"]},
        ),
        migrations.AddIndex(
            model_name="trip",
            index=models.Index(fields=["family", "archived", "starts_on"], name="trip_family_start_idx"),
        ),
        migrations.CreateModel(
            name="TripPhoto",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.CharField(editable=False, max_length=32)),
                ("width", models.PositiveIntegerField()),
                ("height", models.PositiveIntegerField()),
                ("caption", models.CharField(blank=True, max_length=240)),
                ("trip", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="family.trip")),
                ("uploaded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="uploaded_trip_photos", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]
