import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0226_shopping_item_position"),
    ]

    operations = [
        migrations.CreateModel(
            name="BirthdayAgePreference",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("target_key", models.CharField(max_length=64)),
                ("show_age", models.BooleanField(default=True)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="birthday_age_preferences", to="family.family")),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("family", "target_key"), name="birthday_age_preference_target_unique")],
            },
        ),
    ]
