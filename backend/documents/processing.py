import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .consumers import dispatch_processing_consumers
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


class ClaimLost(Exception):
    """Raised when a worker no longer owns the durable processing claim."""


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
    attempts_left = Q(attempts__lt=MAX_ATTEMPTS)
    return attempts_left & (
        Q(status=DocumentProcessingRun.Status.QUEUED)
        | Q(status=DocumentProcessingRun.Status.RETRY, next_retry_at__lte=now)
        | Q(status=DocumentProcessingRun.Status.PROCESSING, lease_expires_at__lte=now)
    )


def _exhausted_due(now):
    return Q(attempts__gte=MAX_ATTEMPTS) & (
        Q(status=DocumentProcessingRun.Status.RETRY, next_retry_at__lte=now)
        | Q(status=DocumentProcessingRun.Status.PROCESSING, lease_expires_at__lte=now)
    )


def _terminalize_exhausted_runs(now, *, batch_size=100):
    """Turn crash-exhausted leases into terminal failures before new claims."""
    exhausted = list(
        DocumentProcessingRun.objects.select_for_update(skip_locked=True)
        .select_related("document")
        .filter(_exhausted_due(now))
        .order_by("queued_at", "created_at")[:batch_size]
    )
    for run in exhausted:
        run.status = DocumentProcessingRun.Status.FAILED
        run.processed_at = now
        run.claim_token = None
        run.lease_expires_at = None
        run.next_retry_at = None
        run.error_code = "attempts_exhausted"
        run.safe_error = "Dokumentverarbeitung wurde nach mehreren fehlgeschlagenen Versuchen beendet."
        run.save(
            update_fields=[
                "status",
                "processed_at",
                "claim_token",
                "lease_expires_at",
                "next_retry_at",
                "error_code",
                "safe_error",
                "updated_at",
            ]
        )
        Document.objects.filter(pk=run.document_id).update(processing_status=Document.ProcessingStatus.FAILED)
        dispatch_processing_consumers(run)
    return len(exhausted)


def claim_next_run(*, now=None, lease_seconds=LEASE_SECONDS):
    """Atomically claim one due job with a unique lease ownership token.

    `select_for_update(skip_locked=True)` lets multiple PostgreSQL workers poll the
    same queue without processing the same run. Expired processing leases are
    claimable while attempts remain, which makes a killed worker restart-safe
    without allowing infinite crash loops. The fresh claim token fences stale
    workers from publishing after another worker reclaimed the run.
    """
    now = now or timezone.now()
    with transaction.atomic():
        _terminalize_exhausted_runs(now)
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
        run.claim_token = uuid.uuid4()
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
                "claim_token",
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
        dispatch_processing_consumers(run)
        return run


def renew_lease(run, *, now=None, lease_seconds=LEASE_SECONDS):
    """Extend a claim only while this worker still owns its fencing token."""
    if not run.claim_token:
        return False
    now = now or timezone.now()
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    updated = DocumentProcessingRun.objects.filter(
        pk=run.pk,
        status=DocumentProcessingRun.Status.PROCESSING,
        claim_token=run.claim_token,
    ).update(lease_expires_at=lease_expires_at, updated_at=now)
    if updated:
        run.lease_expires_at = lease_expires_at
        return True
    return False


def _owns_claim(locked, claimed):
    return (
        locked.status == DocumentProcessingRun.Status.PROCESSING
        and locked.claim_token is not None
        and locked.claim_token == claimed.claim_token
    )


def finish_run(run, result, *, needs_review=True):
    now = timezone.now()
    status = DocumentProcessingRun.Status.REVIEW if needs_review else DocumentProcessingRun.Status.READY
    document_status = Document.ProcessingStatus.REVIEW if needs_review else Document.ProcessingStatus.READY
    with transaction.atomic():
        locked = DocumentProcessingRun.objects.select_for_update().select_related("document").get(pk=run.pk)
        if not _owns_claim(locked, run):
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
        locked.claim_token = None
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
                "claim_token",
                "lease_expires_at",
                "next_retry_at",
                "error_code",
                "safe_error",
                "updated_at",
            ]
        )
        Document.objects.filter(pk=locked.document_id).update(processing_status=document_status)
        dispatch_processing_consumers(locked)
        return locked


def fail_run(run, *, error_code, safe_error, retryable=True, now=None):
    """Fail safely without touching the canonical document file."""
    now = now or timezone.now()
    with transaction.atomic():
        locked = DocumentProcessingRun.objects.select_for_update().select_related("document").get(pk=run.pk)
        if not _owns_claim(locked, run):
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
        locked.claim_token = None
        locked.lease_expires_at = None
        locked.error_code = str(error_code)[:64]
        locked.safe_error = str(safe_error)[:240]
        locked.save(
            update_fields=[
                "status",
                "next_retry_at",
                "processed_at",
                "claim_token",
                "lease_expires_at",
                "error_code",
                "safe_error",
                "updated_at",
            ]
        )
        Document.objects.filter(pk=locked.document_id).update(processing_status=document_status)
        dispatch_processing_consumers(locked)
        return locked
