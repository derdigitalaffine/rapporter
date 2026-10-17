import uuid

from django.conf import settings
from django.db import models

from .models import Family, Routine, Task


class RoutineTaskMigration(models.Model):
    """One-way, user-confirmed handover from the legacy Routine domain to Tasks.

    The legacy row stays protected as compatibility backing for reminder delivery and
    historical RoutineLog data.  `snapshot` is deliberately redundant: it makes the
    migrated Task self-describing even after a later cleanup of the legacy tables.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="routine_task_migrations")
    routine = models.OneToOneField(Routine, on_delete=models.PROTECT, related_name="task_migration")
    task = models.OneToOneField(Task, on_delete=models.PROTECT, related_name="routine_migration")
    snapshot = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="routine_task_migrations")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["family", "routine"], name="routine_task_migration_family_routine_uniq"),
            models.UniqueConstraint(fields=["family", "task"], name="routine_task_migration_family_task_uniq"),
        ]
