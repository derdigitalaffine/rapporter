import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0224_merge_create_preferences_pin_visibility"),
        ("games", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GameTaskAssignment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rule", models.CharField(choices=[("winner", "Winner takes task"), ("loser", "Loser takes task")], max_length=16)),
                ("challenger_confirmed_at", models.DateTimeField()),
                ("opponent_confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("invalidated_at", models.DateTimeField(blank=True, null=True)),
                ("invalidation_reason", models.CharField(blank=True, max_length=64)),
                ("applied_assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("expected_assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("match", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="task_assignment", to="games.gamematch")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="game_assignments", to="family.task")),
            ],
            options={"indexes": [models.Index(fields=["task", "created_at"], name="games_task_stake_idx")]},
        ),
    ]
