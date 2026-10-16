from django.conf import settings
from django.db import models

from .models import Family, Membership, TimestampedModel


class CalDavConnection(TimestampedModel):
    class Scope(models.TextChoices):
        PERSONAL = "personal", "Personal"
        FAMILY = "family", "Family"

    class AccessMode(models.TextChoices):
        READ = "read", "Read only"
        READ_WRITE = "read_write", "Read and write"

    scope = models.CharField(max_length=16, choices=Scope.choices)
    name = models.CharField(max_length=120)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="personal_caldav_connections",
    )
    family = models.ForeignKey(
        Family,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="caldav_connections",
    )
    member = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="caldav_connections",
        help_text="Optional family member whose external calendar this connection projects.",
    )
    access_mode = models.CharField(max_length=16, choices=AccessMode.choices, default=AccessMode.READ)
    calendar_href = models.TextField(blank=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_caldav_connections",
    )
    credentials_encrypted = models.TextField(blank=True, editable=False)
    enabled = models.BooleanField(default=True)
    last_discovered_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["name", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope="personal", owner__isnull=False, family__isnull=True, member__isnull=True)
                    | models.Q(scope="family", owner__isnull=True, family__isnull=False)
                ),
                name="caldav_scope_owner_exactly_one",
            ),
            models.UniqueConstraint(
                fields=["family", "member"],
                condition=models.Q(member__isnull=False),
                name="caldav_one_calendar_per_member",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "enabled"], name="caldav_owner_enabled_idx"),
            models.Index(fields=["family", "enabled"], name="caldav_family_enabled_idx"),
        ]

    @property
    def credential_state(self):
        return "configured" if self.credentials_encrypted else "missing"
