import uuid

from django.db import models


class Notification(models.Model):
    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Important"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="notifications")
    recipient = models.ForeignKey("family.Membership", on_delete=models.CASCADE, related_name="notifications")
    event_type = models.CharField(max_length=96, db_index=True)
    title = models.CharField(max_length=180)
    body = models.TextField(blank=True)
    resource_url = models.CharField(max_length=500, blank=True)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.NORMAL)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["recipient", "read_at", "-created_at"], name="notif_recipient_read_idx"),
            models.Index(fields=["family", "recipient", "-created_at"], name="notif_family_recipient_idx"),
        ]
