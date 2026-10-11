import uuid

from django.conf import settings
from django.db import models


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
