import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0218_note_extended_mode_blocks"),
    ]

    operations = [
        migrations.CreateModel(
            name="TodoPreference",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("smart_ranking_enabled", models.BooleanField(default=True)),
                ("today_sort", models.CharField(choices=[("smart", "Smart"), ("chronological", "Chronological")], default="smart", max_length=16)),
                ("membership", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="todo_preference", to="family.membership")),
            ],
        ),
        migrations.CreateModel(
            name="TodoActionPreference",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("action_id", models.CharField(max_length=48)),
                ("pinned", models.BooleanField(default=False)),
                ("hidden_from_focus", models.BooleanField(default=False)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="todo_action_preferences", to="family.membership")),
            ],
            options={
                "indexes": [models.Index(fields=["membership", "pinned"], name="todo_pref_member_pin_idx")],
                "constraints": [models.UniqueConstraint(fields=("membership", "action_id"), name="todo_action_pref_member_id_uniq")],
            },
        ),
    ]
