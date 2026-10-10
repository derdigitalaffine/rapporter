import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    class ActorClass(models.TextChoices):
        USER = "user", "User"
        SUPERADMIN = "superadmin", "Superadmin"
        SYSTEM = "system", "System"

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        DENIED = "denied", "Denied"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    event_key = models.CharField(max_length=96, db_index=True)
    schema_version = models.PositiveSmallIntegerField(default=1)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    actor_class = models.CharField(max_length=16, choices=ActorClass.choices)
    family = models.ForeignKey(
        "family.Family",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    target_type = models.CharField(max_length=32, blank=True)
    target_id = models.CharField(max_length=128, blank=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    reason = models.CharField(max_length=64, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-occurred_at", "id"]
        indexes = [
            models.Index(fields=["event_key", "occurred_at"], name="audit_event_key_time"),
            models.Index(fields=["family", "occurred_at"], name="audit_family_time"),
            models.Index(fields=["actor", "occurred_at"], name="audit_actor_time"),
            models.Index(fields=["outcome", "occurred_at"], name="audit_outcome_time"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("AuditEvent is append-only.")
        return super().save(*args, **kwargs)


class UsageEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    bucket_start = models.DateTimeField(db_index=True)
    event_key = models.CharField(max_length=64, db_index=True)
    dimension_key = models.CharField(max_length=64, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="usage_events",
    )
    family = models.ForeignKey(
        "family.Family",
        on_delete=models.CASCADE,
        related_name="usage_events",
    )

    class Meta:
        ordering = ["-bucket_start", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "family", "event_key", "bucket_start", "dimension_key"],
                name="usage_event_bucket_unique",
            )
        ]
        indexes = [
            models.Index(fields=["event_key", "bucket_start"], name="usage_event_key_bucket"),
            models.Index(fields=["family", "bucket_start"], name="usage_family_bucket"),
            models.Index(fields=["user", "bucket_start"], name="usage_user_bucket"),
        ]


class DailyRollup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    day = models.DateField(db_index=True)
    metric_key = models.CharField(max_length=96)
    family = models.ForeignKey(
        "family.Family",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="telemetry_rollups",
    )
    dimension_key = models.CharField(max_length=160, blank=True)
    value = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-day", "metric_key", "dimension_key", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["day", "metric_key", "family", "dimension_key"],
                name="daily_rollup_unique",
                nulls_distinct=False,
            )
        ]
        indexes = [
            models.Index(fields=["day", "metric_key"], name="rollup_day_metric"),
            models.Index(fields=["family", "day"], name="rollup_family_day"),
        ]
