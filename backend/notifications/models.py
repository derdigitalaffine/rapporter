import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Important"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    recipient = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="notifications", null=True, blank=True)
    recipient_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="personal_notifications")
    event_type = models.CharField(max_length=96, db_index=True)
    title = models.CharField(max_length=180)
    body = models.TextField(blank=True)
    resource_url = models.CharField(max_length=500, blank=True)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.NORMAL)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(family__isnull=False, recipient__isnull=False, recipient_user__isnull=True) | models.Q(family__isnull=True, recipient__isnull=True, recipient_user__isnull=False), name="notification_recipient_scope")]
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["recipient", "read_at", "-created_at"], name="notif_recipient_read_idx"),
            models.Index(fields=["family", "recipient", "-created_at"], name="notif_family_recipient_idx"),
        ]
