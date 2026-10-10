"""Expense receipt integration for the shared Document Processing Core.

Expense owns receipt semantics (merchant/date/total + review). Documents owns
validation, canonical storage, OCR, quality, retries and worker execution.
"""
from datetime import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from documents.models import Document, DocumentLink, DocumentProcessingRun
from documents.processing import enqueue_document
from documents.quality import assess_canonical_image
from documents.storage import canonicalize_upload, remove_canonical, store_canonical
from family.models import Membership

from .models import Expense, ReceiptExtraction
from .ocr import parse_receipt_text

MAX_RECEIPT_BYTES = 10 * 1024 * 1024
MAX_RECEIPT_TEXT_CHARS = 50_000
PUBLIC_QUALITY_WARNINGS = {"low_resolution", "dark"}


def _validation_message(exc):
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        detail = detail.get("file") or next(iter(detail.values()), None)
    if isinstance(detail, (list, tuple)) and detail:
        detail = detail[0]
    return str(detail or "Der Beleg konnte nicht sicher gelesen werden.")


def canonicalize_receipt_upload(upload):
    """Apply only receipt-specific admission policy, then use Document storage rules."""
    size = getattr(upload, "size", None)
    if size is not None and size > MAX_RECEIPT_BYTES:
        raise ValueError("Der Beleg darf höchstens 10 MB groß sein.")
    try:
        canonical = canonicalize_upload(upload)
    except ValidationError as exc:
        raise ValueError(_validation_message(exc)) from exc
    if not canonical.mime_type.startswith("image/"):
        raise ValueError("Nur JPEG-, PNG- oder WebP-Belege werden unterstützt.")
    quality = assess_canonical_image(canonical)
    warnings = [value for value in quality.get("warnings", []) if value in PUBLIC_QUALITY_WARNINGS]
    return canonical, warnings


def _create_receipt_document(expense, canonical, *, owner_membership, created_by):
    document = Document(
        family=expense.family,
        kind="expense_receipt",
        title="Beleg",
        visibility=Document.Visibility.PRIVATE,
        library_visible=False,
        owner_membership=owner_membership,
        canonical_file="",
        mime_type=canonical.mime_type,
        size=len(canonical.content),
        sha256=canonical.sha256,
        page_count=canonical.page_count,
        created_by=created_by,
    )
    key = store_canonical(document.id, canonical)
    document.canonical_file = key
    document.save(force_insert=True)
    DocumentLink.objects.create(
        document=document,
        domain_type=DocumentLink.DomainType.EXPENSE,
        object_id=expense.id,
        relationship="receipt",
    )
    return document, key


def create_receipt_draft(*, family, paid_by, owner_membership, created_by, canonical, quality_warnings):
    """Create an Expense draft and its hidden private Document atomically."""
    stored_key = None
    try:
        with transaction.atomic():
            expense = Expense.objects.create(
                family=family,
                paid_by=paid_by,
                created_by=created_by,
                source=Expense.Source.RECEIPT,
                status=Expense.Status.DRAFT,
                receipt_status=Expense.ReceiptStatus.QUEUED,
                receipt_mime=canonical.mime_type,
                currency="EUR",
            )
            document, stored_key = _create_receipt_document(
                expense,
                canonical,
                owner_membership=owner_membership,
                created_by=created_by,
            )
            run, _ = enqueue_document(document)
            expense.receipt_document = document
            expense.save(update_fields=["receipt_document", "updated_at"])
            ReceiptExtraction.objects.create(
                expense=expense,
                processing_run=run,
                status=ReceiptExtraction.Status.QUEUED,
                structured_data={"quality_warnings": list(quality_warnings)},
            )
            return expense
    except Exception:
        if stored_key:
            remove_canonical(stored_key)
        raise


def _legacy_canonical(expense):
    content = bytes(expense.receipt_content or b"")
    if not content:
        return None
    upload = SimpleUploadedFile(
        f"legacy-receipt-{expense.id}.bin",
        content,
        content_type=expense.receipt_mime or "application/octet-stream",
    )
    return canonicalize_upload(upload)


def _owner_for_legacy(expense):
    if expense.created_by_id:
        membership = Membership.objects.filter(
            family_id=expense.family_id,
            user_id=expense.created_by_id,
        ).first()
        if membership:
            return membership
    return expense.paid_by


def migrate_legacy_receipt(expense, *, enqueue_pending=True):
    """Idempotently attach a legacy BinaryField receipt to Document Core.

    Legacy bytes remain in place for rollback/dual-read. REVIEW/READY/FAILED
    receipts keep their current domain state; only jobs that were QUEUED or
    PROCESSING are recovered onto the durable Document worker.
    """
    if expense.receipt_document_id:
        return expense.receipt_document, False, False
    canonical = _legacy_canonical(expense)
    if canonical is None:
        return None, False, False

    stored_key = None
    try:
        with transaction.atomic():
            locked = (
                Expense.objects.select_for_update()
                .select_related("paid_by", "receipt_document")
                .get(pk=expense.pk)
            )
            if locked.receipt_document_id:
                return locked.receipt_document, False, False
            owner = _owner_for_legacy(locked)
            document, stored_key = _create_receipt_document(
                locked,
                canonical,
                owner_membership=owner,
                created_by=locked.created_by,
            )
            locked.receipt_document = document
            locked.receipt_mime = canonical.mime_type
            locked.save(update_fields=["receipt_document", "receipt_mime", "updated_at"])

            enqueued = False
            if enqueue_pending and locked.receipt_status in {
                Expense.ReceiptStatus.QUEUED,
                Expense.ReceiptStatus.PROCESSING,
            }:
                run, _ = enqueue_document(document)
                extraction, _ = ReceiptExtraction.objects.get_or_create(expense=locked)
                extraction.processing_run = run
                extraction.status = ReceiptExtraction.Status.QUEUED
                extraction.error = ""
                extraction.processed_at = None
                extraction.save(
                    update_fields=["processing_run", "status", "error", "processed_at", "updated_at"]
                )
                locked.receipt_status = Expense.ReceiptStatus.QUEUED
                locked.save(update_fields=["receipt_status", "updated_at"])
                enqueued = True
            return document, True, enqueued
    except Exception:
        if stored_key:
            remove_canonical(stored_key)
        raise


def queue_receipt_processing(expense):
    """Queue/requeue one receipt on the shared durable Document worker."""
    stored_key = None
    try:
        with transaction.atomic():
            locked = (
                Expense.objects.select_for_update()
                .select_related("paid_by", "receipt_document")
                .get(pk=expense.pk)
            )
            document = locked.receipt_document
            if document is None:
                canonical = _legacy_canonical(locked)
                if canonical is None:
                    raise ValueError("Kein Beleg vorhanden.")
                document, stored_key = _create_receipt_document(
                    locked,
                    canonical,
                    owner_membership=_owner_for_legacy(locked),
                    created_by=locked.created_by,
                )
                locked.receipt_document = document
                locked.receipt_mime = canonical.mime_type
                locked.save(update_fields=["receipt_document", "receipt_mime", "updated_at"])

            run, _ = enqueue_document(document)
            extraction, _ = ReceiptExtraction.objects.get_or_create(expense=locked)
            extraction.processing_run = run
            extraction.status = ReceiptExtraction.Status.QUEUED
            extraction.error = ""
            extraction.processed_at = None
            extraction.save(
                update_fields=["processing_run", "status", "error", "processed_at", "updated_at"]
            )
            locked.receipt_status = Expense.ReceiptStatus.QUEUED
            locked.save(update_fields=["receipt_status", "updated_at"])
            return run
    except Exception:
        if stored_key:
            remove_canonical(stored_key)
        raise


def consume_receipt_processing_run(run, link):
    """Project one shared processing transition into Expense receipt review state."""
    extraction = (
        ReceiptExtraction.objects.select_for_update()
        .select_related("expense")
        .filter(processing_run_id=run.id, expense_id=link.object_id)
        .first()
    )
    if extraction is None:
        return
    expense = extraction.expense
    if expense.receipt_document_id != run.document_id:
        return

    now = timezone.now()
    if run.status == DocumentProcessingRun.Status.PROCESSING:
        extraction.status = ReceiptExtraction.Status.PROCESSING
        extraction.error = ""
        extraction.save(update_fields=["status", "error", "updated_at"])
        Expense.objects.filter(pk=expense.pk, receipt_document_id=run.document_id).update(
            receipt_status=Expense.ReceiptStatus.PROCESSING,
            updated_at=now,
        )
        return

    if run.status in {DocumentProcessingRun.Status.QUEUED, DocumentProcessingRun.Status.RETRY}:
        extraction.status = ReceiptExtraction.Status.QUEUED
        extraction.error = ""
        extraction.processed_at = None
        extraction.save(update_fields=["status", "error", "processed_at", "updated_at"])
        Expense.objects.filter(pk=expense.pk, receipt_document_id=run.document_id).update(
            receipt_status=Expense.ReceiptStatus.QUEUED,
            updated_at=now,
        )
        return

    if run.status == DocumentProcessingRun.Status.FAILED:
        extraction.status = ReceiptExtraction.Status.FAILED
        extraction.processed_at = run.processed_at or now
        extraction.error = (run.safe_error or "Dokumentverarbeitung fehlgeschlagen.")[:500]
        extraction.save(update_fields=["status", "processed_at", "error", "updated_at"])
        Expense.objects.filter(pk=expense.pk, receipt_document_id=run.document_id).update(
            receipt_status=Expense.ReceiptStatus.FAILED,
            updated_at=now,
        )
        return

    if run.status not in {DocumentProcessingRun.Status.REVIEW, DocumentProcessingRun.Status.READY}:
        return

    parsed = parse_receipt_text((run.normalized_text or "")[:MAX_RECEIPT_TEXT_CHARS])
    extraction.raw_text = (run.normalized_text or "")[:MAX_RECEIPT_TEXT_CHARS]
    extraction.merchant = parsed["merchant"]
    extraction.date = parsed["date"]
    extraction.total = parsed["total"]
    extraction.currency = parsed["currency"]
    extraction.field_confidences = parsed["field_confidences"]
    extraction.structured_data = {
        **(extraction.structured_data or {}),
        **parsed["structured_data"],
    }
    extraction.status = ReceiptExtraction.Status.REVIEW
    extraction.processed_at = run.processed_at or now
    extraction.error = ""
    extraction.save(
        update_fields=[
            "raw_text",
            "merchant",
            "date",
            "total",
            "currency",
            "field_confidences",
            "structured_data",
            "status",
            "processed_at",
            "error",
            "updated_at",
        ]
    )

    expense_updates = {
        "receipt_status": Expense.ReceiptStatus.REVIEW,
        "updated_at": now,
    }
    if parsed["merchant"] and not expense.merchant:
        expense_updates["merchant"] = parsed["merchant"]
        expense_updates["title"] = parsed["merchant"]
    if parsed["date"]:
        expense_updates["occurred_at"] = timezone.make_aware(
            datetime.combine(parsed["date"], datetime.min.time())
        )
    if parsed["total"] is not None:
        expense_updates["total_amount"] = parsed["total"]
    if parsed["currency"]:
        expense_updates["currency"] = parsed["currency"]
    Expense.objects.filter(pk=expense.pk, receipt_document_id=run.document_id).update(**expense_updates)
