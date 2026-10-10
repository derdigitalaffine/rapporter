from datetime import datetime

from django.db import transaction
from django.utils import timezone

from documents.consumers import register_document_consumer
from documents.models import DocumentLink, DocumentProcessingRun

from .models import Expense, ReceiptExtraction
from .ocr import MAX_OCR_TEXT_CHARS, parse_receipt_text

_ALLOWED_QUALITY_WARNINGS = {"low_resolution", "dark", "overexposed", "possibly_blurry"}


def _quality_warnings(value):
    found = set()

    def visit(node):
        if isinstance(node, dict):
            warnings = node.get("warnings")
            if isinstance(warnings, list):
                found.update(item for item in warnings if item in _ALLOWED_QUALITY_WARNINGS)
            for child in node.values():
                if isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value or {})
    return sorted(found)


def _consume_receipt_run(run, link):
    with transaction.atomic():
        extraction = (
            ReceiptExtraction.objects.select_for_update()
            .select_related("expense")
            .filter(
                expense_id=link.object_id,
                expense__receipt_document_id=run.document_id,
                processing_run_id=run.id,
            )
            .first()
        )
        if not extraction:
            return
        expense = extraction.expense
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
            extraction.save(update_fields=["status", "error", "updated_at"])
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

        text = (run.normalized_text or "")[:MAX_OCR_TEXT_CHARS]
        parsed = parse_receipt_text(text)
        warnings = _quality_warnings(run.quality_data)
        extraction.raw_text = text
        extraction.merchant = parsed["merchant"]
        extraction.date = parsed["date"]
        extraction.total = parsed["total"]
        extraction.currency = parsed["currency"]
        extraction.field_confidences = parsed["field_confidences"]
        extraction.structured_data = {
            **(extraction.structured_data or {}),
            **parsed["structured_data"],
            "quality_warnings": warnings,
            "document_processing_run": str(run.id),
            "document_extractor": run.extractor,
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

        updates = {"receipt_status": Expense.ReceiptStatus.REVIEW, "updated_at": now}
        if parsed["merchant"] and not expense.merchant:
            updates["merchant"] = parsed["merchant"]
            updates["title"] = parsed["merchant"]
        if parsed["date"]:
            updates["occurred_at"] = timezone.make_aware(datetime.combine(parsed["date"], datetime.min.time()))
        if parsed["total"] is not None:
            updates["total_amount"] = parsed["total"]
        if parsed["currency"]:
            updates["currency"] = parsed["currency"]
        Expense.objects.filter(pk=expense.pk, receipt_document_id=run.document_id).update(**updates)


def consume_receipt_document(run, link):
    """Expense-owned projection of one shared DocumentProcessingRun."""
    try:
        _consume_receipt_run(run, link)
    except Exception:
        # A domain parser failure must not turn successful generic OCR into a
        # failed Document run. Persist a redacted Expense-side failure instead.
        now = timezone.now()
        ReceiptExtraction.objects.filter(processing_run_id=run.id).update(
            status=ReceiptExtraction.Status.FAILED,
            processed_at=now,
            error="Belegauswertung ist unerwartet fehlgeschlagen.",
            updated_at=now,
        )
        Expense.objects.filter(receipt_document_id=run.document_id).update(
            receipt_status=Expense.ReceiptStatus.FAILED,
            updated_at=now,
        )


register_document_consumer(DocumentLink.DomainType.EXPENSE, consume_receipt_document)
