import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from family.models import Family, Membership


class Document(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private"
        FAMILY = "family", "Family"
        SELECTED = "selected", "Selected"

    class ProcessingStatus(models.TextChoices):
        STORED = "stored", "Stored"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        REVIEW = "review", "Review"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=64, default="generic")
    title = models.CharField(max_length=240)
    document_date = models.DateField(null=True, blank=True)
    correspondent = models.CharField(max_length=180, blank=True)
    visibility = models.CharField(max_length=16, choices=Visibility.choices, default=Visibility.PRIVATE, db_index=True)
    owner_membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="owned_documents")
    canonical_file = models.CharField(max_length=500, editable=False)
    mime_type = models.CharField(max_length=96, editable=False)
    size = models.PositiveBigIntegerField(editable=False)
    sha256 = models.CharField(max_length=64, db_index=True, editable=False)
    page_count = models.PositiveIntegerField(default=1, editable=False)
    processing_status = models.CharField(max_length=16, choices=ProcessingStatus.choices, default=ProcessingStatus.STORED, db_index=True)
    pinned = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="documents_created")
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-document_date", "-created_at"]
        indexes = [
            models.Index(fields=["family", "sha256", "archived_at"], name="doc_family_hash_arch_idx"),
            models.Index(fields=["family", "visibility", "archived_at"], name="doc_family_vis_arch_idx"),
        ]


class DocumentAccess(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="access_entries")
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="document_access_entries")
    can_view = models.BooleanField(default=True)
    can_manage = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["document", "membership"], name="document_access_member_uniq"),
        ]


class DocumentLink(models.Model):
    class DomainType(models.TextChoices):
        EXPENSE = "expense", "Expense"
        PET = "pet", "Pet"
        SCHOOL = "school", "School"
        CONTRACT = "contract", "Contract"
        EVENT = "event", "Event"
        TASK = "task", "Task"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="domain_links")
    domain_type = models.CharField(max_length=32, choices=DomainType.choices)
    object_id = models.UUIDField()
    relationship = models.CharField(max_length=48, default="source")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document", "domain_type", "object_id", "relationship"],
                name="document_domain_link_uniq",
            ),
        ]
        indexes = [models.Index(fields=["domain_type", "object_id"], name="document_domain_obj_idx")]


class DocumentProcessingRun(models.Model):
    """Durable execution record for the local document-processing pipeline.

    A run is intentionally separate from :class:`Document`: the canonical file is
    never replaced or deleted when extraction fails, and every retry remains
    operationally observable without leaking raw document contents to logs.
    """

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        RETRY = "retry", "Retry"
        REVIEW = "review", "Review"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="processing_runs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    pipeline_version = models.CharField(max_length=32, default="1")
    extractor = models.CharField(max_length=64, blank=True)
    language = models.CharField(max_length=24, blank=True)
    normalized_text = models.TextField(blank=True)
    quality_data = models.JSONField(default=dict, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    claim_token = models.UUIDField(null=True, blank=True, editable=False)
    queued_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["queued_at", "created_at"]
        indexes = [
            models.Index(fields=["status", "next_retry_at", "queued_at"], name="docproc_status_retry_idx"),
            models.Index(fields=["status", "lease_expires_at"], name="docproc_lease_idx"),
        ]


class ExtractedField(models.Model):
    class SourceType(models.TextChoices):
        EXPLICIT = "explicit", "Explicit"
        DERIVED = "derived", "Derived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    processing_run = models.ForeignKey(DocumentProcessingRun, on_delete=models.CASCADE, related_name="extracted_fields")
    key = models.CharField(max_length=96)
    value_json = models.JSONField()
    confidence = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    page = models.PositiveIntegerField(null=True, blank=True)
    bbox = models.JSONField(null=True, blank=True)
    evidence_text = models.TextField(blank=True)
    source_type = models.CharField(max_length=16, choices=SourceType.choices, default=SourceType.EXPLICIT)
    extractor_version = models.CharField(max_length=64, default="1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["key", "page", "created_at"]
        indexes = [models.Index(fields=["processing_run", "key"], name="docfield_run_key_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="docfield_confidence_0_1",
            ),
        ]
