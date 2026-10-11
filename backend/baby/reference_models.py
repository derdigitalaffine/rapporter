import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class PediatricReferencePackage(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        SUPERSEDED = "superseded", "Superseded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    source_key = models.CharField(max_length=64)
    source_title = models.CharField(max_length=200)
    source_version = models.CharField(max_length=96)
    locale = models.CharField(max_length=16, default="de-DE")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    imported_at = models.DateTimeField()
    checksum = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    reason = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pediatric_reference_packages_created",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pediatric_reference_packages_published",
    )
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supersedes",
    )

    class Meta:
        ordering = ["source_key", "locale", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_key", "source_version", "locale"],
                name="baby_ped_ref_source_version_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["source_key", "locale", "status", "effective_from"],
                name="baby_ped_ref_lookup_idx",
            )
        ]

    def save(self, *args, **kwargs):
        # A package can be reviewed/imported ahead of time, but publishing is
        # the activation step in this MVP. Keeping future-effective packages in
        # draft prevents them from superseding today's valid package early.
        if self.status == self.Status.PUBLISHED and self.effective_from and self.effective_from > timezone.localdate():
            raise ValidationError("Future-effective pediatric reference packages must remain draft until their effective date.")
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "status",
                "source_key",
                "source_title",
                "source_version",
                "locale",
                "published_at",
                "effective_from",
                "effective_to",
                "imported_at",
                "checksum",
                "payload",
                "reason",
                "notes",
                "created_by_id",
                "published_by_id",
            ).first()
            if previous and previous["status"] in {self.Status.PUBLISHED, self.Status.SUPERSEDED}:
                protected = (
                    "source_key",
                    "source_title",
                    "source_version",
                    "locale",
                    "published_at",
                    "effective_from",
                    "effective_to",
                    "imported_at",
                    "checksum",
                    "payload",
                    "reason",
                    "notes",
                    "created_by_id",
                    "published_by_id",
                )
                for field in protected:
                    if previous[field] != getattr(self, field):
                        raise ValidationError("Published pediatric reference packages are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.Status.DRAFT:
            raise ValidationError("Published pediatric reference packages cannot be deleted.")
        return super().delete(*args, **kwargs)


class PediatricPreventiveEventReference(models.Model):
    """Private, immutable provenance for a generic family calendar event."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    baby = models.ForeignKey(
        "baby.BabyProfile",
        on_delete=models.CASCADE,
        related_name="preventive_event_references",
    )
    event = models.OneToOneField(
        "family.FamilyEvent",
        on_delete=models.CASCADE,
        related_name="pediatric_private_reference",
    )
    reference_package = models.ForeignKey(
        PediatricReferencePackage,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="preventive_event_references",
    )
    source_key = models.CharField(max_length=64)
    source_version = models.CharField(max_length=96)
    source_checksum = models.CharField(max_length=64, blank=True)
    locale = models.CharField(max_length=16, default="de-DE")
    rule_key = models.CharField(max_length=64)
    start_day = models.PositiveIntegerField()
    end_day = models.PositiveIntegerField()
    target_day = models.PositiveIntegerField()

    class Meta:
        ordering = ["baby_id", "target_day", "rule_key"]
        indexes = [
            models.Index(fields=["baby", "source_key", "source_version"], name="baby_ped_event_ref_idx")
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(
                "baby_id",
                "event_id",
                "reference_package_id",
                "source_key",
                "source_version",
                "source_checksum",
                "locale",
                "rule_key",
                "start_day",
                "end_day",
                "target_day",
            ).first()
            if previous:
                for field, value in previous.items():
                    if value != getattr(self, field):
                        raise ValidationError("Preventive event reference provenance is immutable.")
        return super().save(*args, **kwargs)
