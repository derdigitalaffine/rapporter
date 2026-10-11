import uuid

from django.conf import settings
from django.db import models


class TaskChecklistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("family.Task", on_delete=models.CASCADE, related_name="checklist_items")
    title = models.CharField(max_length=180)
    position = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    extracted_task = models.OneToOneField(
        "family.Task",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_checklist_item",
    )
    extracted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_task_checklist_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at", "id"]
        indexes = [models.Index(fields=["task", "position"], name="task_checklist_order_idx")]


class TaskExternalLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("family.Task", on_delete=models.CASCADE, related_name="external_links")
    url = models.URLField(max_length=2048)
    label = models.CharField(max_length=120, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_task_external_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["task", "url"], name="task_external_link_url_uniq"),
        ]
        indexes = [models.Index(fields=["task", "position"], name="task_external_order_idx")]
