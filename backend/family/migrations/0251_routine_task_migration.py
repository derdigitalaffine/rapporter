import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0250_shopping_reference_records"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RoutineTaskMigration",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("snapshot", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="routine_task_migrations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "family",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="routine_task_migrations",
                        to="family.family",
                    ),
                ),
                (
                    "routine",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="task_migration",
                        to="family.routine",
                    ),
                ),
                (
                    "task",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="routine_migration",
                        to="family.task",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "constraints": [
                    models.UniqueConstraint(fields=("family", "routine"), name="routine_task_migration_family_routine_uniq"),
                    models.UniqueConstraint(fields=("family", "task"), name="routine_task_migration_family_task_uniq"),
                ],
            },
        ),
    ]
