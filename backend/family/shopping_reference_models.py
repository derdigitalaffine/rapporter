import uuid

from django.db import models

from .models import TimestampedModel


class ReferenceDataset(TimestampedModel):
    """Versioned public shopping reference package.

    This registry is intentionally global: reference packages must never carry
    Family/User ownership or become a second source of truth for ShoppingItem.
    Household corrections and observations live in their existing private
    domains and are not stored here.
    """

    class DatasetType(models.TextChoices):
        STORE_REFERENCE = "store_reference", "Store reference"
        LEXICON = "lexicon", "Lexicon"
        GTIN_PRODUCT = "gtin_product", "GTIN product"
        STORE_LAYOUT_EVIDENCE = "store_layout_evidence", "Store layout evidence"

    class State(models.TextChoices):
        STAGED = "staged", "Staged"
        VALIDATING = "validating", "Validating"
        PREVIEW = "preview", "Preview"
        ACTIVATING = "activating", "Activating"
        ACTIVE = "active", "Active"
        FAILED = "failed", "Failed"
        STALE = "stale", "Stale / update available"
        DISABLED = "disabled", "Disabled"
        ROLLBACK = "rollback", "Rollback"

    class Redistribution(models.TextChoices):
        ADOPT = "adopt", "Adopt"
        ADAPT = "adapt", "Adapt"
        DEFER = "defer", "Defer"
        DENY = "deny", "Deny"

    dataset_id = models.CharField(max_length=180)
    dataset_type = models.CharField(max_length=40, choices=DatasetType.choices)
    schema_version = models.PositiveIntegerField()
    version = models.CharField(max_length=80)
    source_adapter = models.CharField(max_length=64, blank=True, default="")
    source_url = models.URLField(max_length=1000, blank=True)
    source_revision = models.CharField(max_length=200, blank=True)
    locale = models.CharField(max_length=32, blank=True)
    country = models.CharField(max_length=2, blank=True)
    region = models.CharField(max_length=120, blank=True)
    licence = models.CharField(max_length=120)
    attribution = models.TextField(blank=True)
    redistribution = models.CharField(max_length=16, choices=Redistribution.choices)
    checksum = models.CharField(max_length=128)
    coverage = models.JSONField(default=dict, blank=True)
    quality = models.JSONField(default=dict, blank=True)
    dependencies = models.JSONField(default=list, blank=True)
    manifest = models.JSONField(default=dict, blank=True)
    package_size_bytes = models.PositiveBigIntegerField(default=0)
    record_count = models.PositiveBigIntegerField(default=0)
    validation_summary = models.JSONField(default=dict, blank=True)
    validation_error = models.TextField(blank=True)
    state = models.CharField(max_length=24, choices=State.choices, default=State.STAGED, db_index=True)
    state_revision = models.PositiveBigIntegerField(default=0)
    fetched_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    installed_at = models.DateTimeField(null=True, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["dataset_id", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["dataset_id", "version"], name="refds_id_version_uniq"),
            models.UniqueConstraint(
                fields=["dataset_id"],
                condition=models.Q(state="active"),
                name="refds_one_active_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["dataset_type", "state"], name="refds_type_state_idx"),
            models.Index(fields=["dataset_id", "state"], name="refds_id_state_idx"),
        ]

    def __str__(self):
        return f"{self.dataset_id}@{self.version}"


class ReferenceDatasetLease(TimestampedModel):
    """Short technical lease serialising operations for one semantic dataset."""

    dataset_id = models.CharField(max_length=180, unique=True)
    owner = models.CharField(max_length=128)
    token = models.UUIDField(default=uuid.uuid4, editable=False)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["dataset_id"]


class ReferenceDatasetActivationEvent(TimestampedModel):
    """Append-only technical activation history without household identifiers."""

    class Action(models.TextChoices):
        ACTIVATE = "activate", "Activate"
        DISABLE = "disable", "Disable"
        ROLLBACK = "rollback", "Rollback"

    dataset_id = models.CharField(max_length=180, db_index=True)
    action = models.CharField(max_length=16, choices=Action.choices)
    from_version = models.CharField(max_length=80, blank=True)
    to_version = models.CharField(max_length=80, blank=True)
    state_revision = models.PositiveBigIntegerField(default=0)
    reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["dataset_id", "-created_at"], name="refds_event_time_idx"),
        ]
