from django.core.files.base import ContentFile
from django.db import transaction
from rest_framework.exceptions import ValidationError

from documents.models import Document, DocumentLink
from documents.processing import enqueue_document
from documents.storage import canonicalize_upload, remove_canonical, store_canonical
from family.models import Membership

from .models import Expense, ReceiptExtraction

MAX_RECEIPT_BYTES = 10 * 1024 * 1024
ALLOWED_RECEIPT_MIME = {"image/jpeg", "image/png", "image/webp"}


def _validation_message(exc):
    detail = getattr(exc, "detail", exc)
    if isinstance(detail, dict):
        detail = detail.get("file", next(iter(detail.values()), "Ungültiger Beleg."))
    if isinstance(detail, (list, tuple)):
        detail = detail[0] if detail else "Ungültiger Beleg."
    return str(detail)


def canonicalize_receipt_upload(upload):
    """Apply receipt-specific limits, then delegate canonicalization to Documents."""
    size = getattr(upload, "size", None)
    if size is not None and size > MAX_RECEIPT_BYTES:
        raise ValueError("Der Beleg darf höchstens 10 MB groß sein.")
    try:
        canonical = canonicalize_upload(upload)
    except ValidationError as exc:
        raise ValueError(_validation_message(exc)) from exc
    if canonical.mime_type not in ALLOWED_RECEIPT_MIME:
        raise ValueError("Nur JPEG-, PNG- oder WebP-Belege werden unterstützt.")
    return canonical


def build_receipt_document(expense, canonical, *, owner_membership, created_by):
    """Store canonical bytes and return an unsaved domain-owned Document."""
    document = Document(
        family=expense.family,
        kind="receipt",
        title=(expense.title or expense.merchant or "Beleg")[:240],
        visibility=Document.Visibility.PRIVATE,
        owner_membership=owner_membership,
        mime_type=canonical.mime_type,
        size=len(canonical.content),
        sha256=canonical.sha256,
        page_count=canonical.page_count,
        created_by=created_by,
    )
    key = store_canonical(document.id, canonical)
    document.canonical_file = key
    return document, key


def link_receipt_document(expense, document):
    DocumentLink.objects.get_or_create(
        document=document,
        domain_type=DocumentLink.DomainType.EXPENSE,
        object_id=expense.id,
        relationship="receipt",
    )


def migrate_legacy_receipt(expense):
    """Idempotently move one legacy BinaryField receipt onto the shared core.

    The legacy bytes remain in place during the dual-read rollback window. New
    processing is queued on the canonical Document and ReceiptExtraction points at
    that run; a later cleanup migration may remove the BinaryField only after the
    repository no longer needs rollback compatibility.
    """
    with transaction.atomic():
        locked = Expense.objects.select_for_update().select_related("paid_by", "created_by").get(pk=expense.pk)
        if locked.receipt_document_id:
            return locked.receipt_document, getattr(locked, "extraction", None)
        content = bytes(locked.receipt_content or b"")
        if not content:
            return None, getattr(locked, "extraction", None)
        owner = None
        if locked.created_by_id:
            owner = Membership.objects.filter(family=locked.family, user_id=locked.created_by_id).first()
        owner = owner or locked.paid_by

    canonical = canonicalize_receipt_upload(ContentFile(content, name="legacy-receipt"))
    document, key = build_receipt_document(locked, canonical, owner_membership=owner, created_by=locked.created_by)
    try:
        with transaction.atomic():
            current = Expense.objects.select_for_update().get(pk=locked.pk)
            if current.receipt_document_id:
                remove_canonical(key)
                return current.receipt_document, getattr(current, "extraction", None)
            document.save(force_insert=True)
            link_receipt_document(current, document)
            run, _ = enqueue_document(document)
            current.receipt_document = document
            current.receipt_mime = canonical.mime_type
            current.save(update_fields=["receipt_document", "receipt_mime", "updated_at"])
            extraction, _ = ReceiptExtraction.objects.get_or_create(expense=current)
            extraction.processing_run = run
            if extraction.status in {ReceiptExtraction.Status.QUEUED, ReceiptExtraction.Status.PROCESSING, ReceiptExtraction.Status.FAILED}:
                extraction.status = ReceiptExtraction.Status.QUEUED
                extraction.error = ""
                extraction.processed_at = None
            extraction.save(update_fields=["processing_run", "status", "error", "processed_at", "updated_at"])
            return document, extraction
    except Exception:
        remove_canonical(key)
        raise
