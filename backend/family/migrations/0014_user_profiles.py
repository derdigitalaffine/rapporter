import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0013_shopping_prediction_history"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("avatar_key", models.CharField(blank=True, max_length=64)),
                ("avatar_version", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("birth_month", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("birth_day", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("birth_year", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="familyos_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name="membership",
            name="birthday_visibility",
            field=models.CharField(choices=[("hidden", "Hidden"), ("day_month", "Day and month"), ("full_date", "Full date")], default="day_month", max_length=16),
        ),
    ]
