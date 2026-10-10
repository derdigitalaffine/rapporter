import uuid

from django.conf import settings
from django.db import models

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
