from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Document, DocumentProcessingRun, ExtractedField

PIPELINE_VERSION = "1"
MAX_ATTEMPTS = 4
LEASE_SECONDS = 10 * 60
RETRY_BASE_SECONDS = 30
ACTIVE_STATUSES = {
    DocumentProcessingRun.Status.QUEUED,
    DocumentProcessingRun.Status.PROCESSING,
    DocumentProcessingRun.Status.RETRY,
}


def enqueue_document(document, *, pipeline_version=PIPELINE_VERSION):
    """Create at most one active run for a document and mark it queued."""
    with transaction.atomic():
        locked = Document.objects.select_for_update().get(pk=document.pk)
        existing = (
            locked.processing_runs.filter(status__in=ACTIVE_STATUSES)
            .order_by("queued_at")
            .first()
        )
        if existing:
            return existing, False
        run = DocumentProcessingRun.objects.create(
            document=locked,
            status=DocumentProcessingRun.Status.QUEUED,
            pipeline_version=pipeline_version,
        )
        if locked.processing_status != Document.ProcessingStatus.QUEUED:
            locked.processing_status = Document.ProcessingStatus.QUEUED
            locked.save(update_fields=["processing_status", "updated_at"])
        return run, True


def _claimable(now):
    return (
        Q(status=DocumentProcessingRun.Status.QUEUED)
        | Q(status=DocumentProcessingRun.Status.RETRY, next_retry_at__lte=now)
        | Q(status=DocumentProcessingRun.Status.PROCESSING, lease_expires_at__lte=now)
    )


def claim_next_run(*, now=None, lease_seconds=LEASE_SECONDS):
    """Atomically claim one due job.

    `select_for_update(skip_locked=True)` lets multiple PostgreSQL workers poll the
    same queue without processing the same run. Expired processing leases are
    claimable, which makes a killed worker restart-safe.
    """
    now = now or timezone.now()
    with transaction.atomic():
        run = (
            DocumentProcessingRun.objects.select_for_update(skip_locked=True)
            .select_related("document")
            .filter(_claimable(now))
            .order_by("queued_at", "created_at")
            .first()
        )
        if not run:
            return None
        run.status = DocumentProcessingRun.Status.PROCESSING
        run.attempts += 1
        run.started_at = run.started_at or now
        run.processing_started_at = now
        run.lease_expires_at = now + timedelta(seconds=lease_seconds)
        run.next_retry_at = None
        run.error_code = ""
        run.safe_error = ""
        run.save(
            update_fields=[
                "status",
                "attempts",
                "started_at",
                "processing_started_at",
                "lease_expires_at",
                "next_retry_at",
                "error_code",
                "safe_error",
                "updated_at",
            ]
        )
        Document.objects.filter(pk=run.document_id).update(processing_status=Document.ProcessingStatus.PROCESSING)
        return run


def finish_run(run, result, *, needs_review=True):
    now = timezone.now()
    status = DocumentProcessingRun.Status.REVIEW if needs_review else DocumentProcessingRun.Status.READY
    document_status = Document.ProcessingStatus.REVIEW if needs_review else Document.ProcessingStatus.READY
    with transaction.atomic():
        locked = DocumentProcessingRun.objects.select_for_update().get(pk=run.pk)
        if locked.status != DocumentProcessingRun.Status.PROCESSING:
            return locked
        locked.extracted_fields.all().delete()
        ExtractedField.objects.bulk_create(
            [
                ExtractedField(
                    processing_run=locked,
                    key=field["key"],
                    value_json=field["value_json"],
                    confidence=field.get("confidence", 0),
                    page=field.get("page"),
                    bbox=field.get("bbox"),
                    evidence_text=field.get("evidence_text", "")[:2000],
                    source_type=field.get("source_type", ExtractedField.SourceType.EXPLICIT),
                    extractor_version=field.get("extractor_version", locked.pipeline_version),
                )
                for field in result.fields
            ]
        )
        locked.status = status
        locked.extractor = result.extractor[:64]
        locked.language = result.language[:24]
        locked.normalized_text = result.text
        locked.quality_data = result.quality_data
        locked.processed_at = now
        locked.lease_expires_at = None
        locked.next_retry_at = None
        locked.error_code = ""
        locked.safe_error = ""
        locked.save(
            update_fields=[
                "status",
                "extractor",
                "language",
                "normalized_text",
                "quality_data",
                "processed_at",
                "lease_expires_at",
                "next_retry_at",
                "error_code",
                "safe_error",
                "updated_at",
            ]
        )
        Document.objects.filter(pk=locked.document_id).update(processing_status=document_status)
        return locked


def fail_run(run, *, error_code, safe_error, retryable=True, now=None):
    """Fail safely without touching the canonical document file."""
    now = now or timezone.now()
    with transaction.atomic():
        locked = DocumentProcessingRun.objects.select_for_update().get(pk=run.pk)
        if locked.status != DocumentProcessingRun.Status.PROCESSING:
            return locked
        should_retry = retryable and locked.attempts < MAX_ATTEMPTS
        if should_retry:
            delay = RETRY_BASE_SECONDS * (2 ** max(0, locked.attempts - 1))
            locked.status = DocumentProcessingRun.Status.RETRY
            locked.next_retry_at = now + timedelta(seconds=delay)
            document_status = Document.ProcessingStatus.QUEUED
        else:
            locked.status = DocumentProcessingRun.Status.FAILED
            locked.next_retry_at = None
            locked.processed_at = now
            document_status = Document.ProcessingStatus.FAILED
        locked.lease_expires_at = None
        locked.error_code = str(error_code)[:64]
        locked.safe_error = str(safe_error)[:240]
        locked.save(
            update_fields=[
                "status",
                "next_retry_at",
                "processed_at",
                "lease_expires_at",
                "error_code",
                "safe_error",
                "updated_at",
            ]
        )
        Document.objects.filter(pk=locked.document_id).update(processing_status=document_status)
        return locked
