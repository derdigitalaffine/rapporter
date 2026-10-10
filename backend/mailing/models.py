import uuid

from django.db import models


class TransactionalEmail(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        RETRY = "retry", "Retry"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message_key = models.CharField(max_length=180, unique=True)
    template_key = models.CharField(max_length=80)
    locale = models.CharField(max_length=8, default="de")
    recipient = models.EmailField(blank=True, default="")
    recipient_hash = models.CharField(max_length=64, db_index=True)
    context = models.JSONField(default=dict, blank=True)
    reference_type = models.CharField(max_length=80, blank=True, default="")
    reference_id = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(db_index=True)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error_code = models.CharField(max_length=80, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    payload_cleared_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="mail_status_due_idx"),
            models.Index(fields=["status", "lease_expires_at"], name="mail_status_lease_idx"),
        ]
