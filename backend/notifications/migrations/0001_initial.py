import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("family", "0220_pinboard_adapter_keys"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(db_index=True, max_length=96)),
                ("title", models.CharField(max_length=180)),
                ("body", models.TextField(blank=True)),
                ("resource_url", models.CharField(blank=True, max_length=500)),
                ("priority", models.CharField(choices=[("normal", "Normal"), ("important", "Important")], default="normal", max_length=16)),
                ("read_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="family.family")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="family.membership")),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["recipient", "read_at", "-created_at"], name="notif_recipient_read_idx"),
                    models.Index(fields=["family", "recipient", "-created_at"], name="notif_family_recipient_idx"),
                ],
            },
        ),
    ]
