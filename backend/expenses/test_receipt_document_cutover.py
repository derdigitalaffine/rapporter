import io
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient
from unittest.mock import patch

from documents.models import Document, DocumentLink, DocumentProcessingRun
from family.models import Family, Membership

from .document_consumer import consume_receipt_document
from .models import Expense, ReceiptExtraction
from .receipt_documents import migrate_legacy_receipt

User = get_user_model()


class ReceiptDocumentCutoverTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="receipt-owner", password="test")
        self.family = Family.objects.create(name="Receipt Family", slug="receipt-family")
        self.member = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Owner",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.tmp = tempfile.TemporaryDirectory()
        self.storage_patch = patch("documents.storage.default_storage", FileSystemStorage(location=self.tmp.name))
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.tmp.cleanup()

    def image_bytes(self):
        output = io.BytesIO()
        Image.new("RGB", (900, 1200), "white").save(output, "PNG")
        return output.getvalue()

    def upload(self):
        return self.client.post(
            "/api/expenses/receipt/",
            {
                "family": str(self.family.id),
                "receipt": SimpleUploadedFile("receipt.png", self.image_bytes(), content_type="image/png"),
            },
            format="multipart",
        )

    def test_document_result_projects_into_existing_expense_review_contract(self):
        response = self.upload()
        self.assertEqual(response.status_code, 202, response.data)
        expense = Expense.objects.get(pk=response.data["id"])
        extraction = ReceiptExtraction.objects.get(expense=expense)
        run = extraction.processing_run
        run.status = DocumentProcessingRun.Status.REVIEW
        run.normalized_text = "REWE MARKT\n08.10.2026\nSUMME EUR 12,34\nRÜCKGELD 7,66"
        run.extractor = "fixture"
        run.quality_data = {"pages": [{"quality": {"warnings": ["dark", "low_resolution"]}}]}
        run.processed_at = timezone.now()
        run.save(update_fields=["status", "normalized_text", "extractor", "quality_data", "processed_at", "updated_at"])
        link = DocumentLink.objects.get(document=run.document, domain_type=DocumentLink.DomainType.EXPENSE)

        consume_receipt_document(run, link)

        expense.refresh_from_db()
        extraction.refresh_from_db()
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.REVIEW)
        self.assertEqual(expense.merchant, "REWE MARKT")
        self.assertEqual(str(expense.total_amount), "12.34")
        self.assertEqual(extraction.status, ReceiptExtraction.Status.REVIEW)
        self.assertEqual(extraction.structured_data["quality_warnings"], ["dark", "low_resolution"])
        self.assertEqual(extraction.structured_data["document_processing_run"], str(run.id))
        self.assertGreater(extraction.field_confidences["total"], 0.8)

    def test_stale_run_cannot_overwrite_a_newer_retry(self):
        response = self.upload()
        expense = Expense.objects.get(pk=response.data["id"])
        extraction = ReceiptExtraction.objects.get(expense=expense)
        old_run = extraction.processing_run
        newer = DocumentProcessingRun.objects.create(document=expense.receipt_document)
        extraction.processing_run = newer
        extraction.status = ReceiptExtraction.Status.QUEUED
        extraction.save(update_fields=["processing_run", "status", "updated_at"])
        old_run.status = DocumentProcessingRun.Status.REVIEW
        old_run.normalized_text = "OLD SHOP\nSUMME EUR 99,99"
        old_run.save(update_fields=["status", "normalized_text", "updated_at"])
        link = DocumentLink.objects.get(document=old_run.document, domain_type=DocumentLink.DomainType.EXPENSE)

        consume_receipt_document(old_run, link)

        extraction.refresh_from_db()
        expense.refresh_from_db()
        self.assertEqual(extraction.processing_run_id, newer.id)
        self.assertEqual(extraction.status, ReceiptExtraction.Status.QUEUED)
        self.assertNotEqual(expense.merchant, "OLD SHOP")

    def test_retry_reuses_the_existing_active_document_run(self):
        response = self.upload()
        expense = Expense.objects.get(pk=response.data["id"])
        extraction = ReceiptExtraction.objects.get(expense=expense)
        original_run_id = extraction.processing_run_id

        retry = self.client.post(f"/api/expenses/{expense.id}/retry-receipt/", {}, format="json")

        self.assertEqual(retry.status_code, 202, retry.data)
        extraction.refresh_from_db()
        self.assertEqual(extraction.processing_run_id, original_run_id)
        self.assertEqual(
            DocumentProcessingRun.objects.filter(document=expense.receipt_document, status=DocumentProcessingRun.Status.QUEUED).count(),
            1,
        )

    def test_delete_removes_domain_owned_document_and_extraction(self):
        response = self.upload()
        expense = Expense.objects.get(pk=response.data["id"])
        document_id = expense.receipt_document_id
        self.assertEqual(self.client.get(f"/api/expenses/{expense.id}/receipt-file/").status_code, 200)

        deleted = self.client.delete(f"/api/expenses/{expense.id}/receipt-file/")

        self.assertEqual(deleted.status_code, 204)
        expense.refresh_from_db()
        self.assertIsNone(expense.receipt_document_id)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.NONE)
        self.assertFalse(Document.objects.filter(pk=document_id).exists())
        self.assertFalse(ReceiptExtraction.objects.filter(expense=expense).exists())
        self.assertEqual(self.client.get(f"/api/expenses/{expense.id}/receipt-file/").status_code, 404)

    def test_legacy_backfill_is_idempotent_and_keeps_binary_for_rollback(self):
        expense = Expense.objects.create(
            family=self.family,
            title="Legacy",
            paid_by=self.member,
            created_by=self.user,
            source=Expense.Source.RECEIPT,
            status=Expense.Status.DRAFT,
            receipt_status=Expense.ReceiptStatus.REVIEW,
            receipt_content=self.image_bytes(),
            receipt_mime="image/png",
        )
        extraction = ReceiptExtraction.objects.create(expense=expense, status=ReceiptExtraction.Status.REVIEW)

        first_document, first_extraction = migrate_legacy_receipt(expense)
        second_document, second_extraction = migrate_legacy_receipt(Expense.objects.get(pk=expense.pk))

        expense.refresh_from_db()
        extraction.refresh_from_db()
        self.assertEqual(first_document.id, second_document.id)
        self.assertEqual(first_extraction.id, second_extraction.id)
        self.assertTrue(expense.receipt_content)
        self.assertEqual(expense.receipt_document_id, first_document.id)
        self.assertEqual(extraction.status, ReceiptExtraction.Status.REVIEW)
        self.assertEqual(extraction.processing_run.document_id, first_document.id)
        self.assertEqual(DocumentLink.objects.filter(document=first_document, object_id=expense.id).count(), 1)

    def test_terminal_document_failure_is_projected_without_raw_exception_detail(self):
        response = self.upload()
        expense = Expense.objects.get(pk=response.data["id"])
        extraction = ReceiptExtraction.objects.get(expense=expense)
        run = extraction.processing_run
        run.status = DocumentProcessingRun.Status.FAILED
        run.safe_error = "Lokale OCR konnte die Seite nicht verarbeiten."
        run.error_code = "ocr_failed"
        run.processed_at = timezone.now()
        run.save(update_fields=["status", "safe_error", "error_code", "processed_at", "updated_at"])
        link = DocumentLink.objects.get(document=run.document, domain_type=DocumentLink.DomainType.EXPENSE)

        consume_receipt_document(run, link)

        extraction.refresh_from_db()
        expense.refresh_from_db()
        self.assertEqual(extraction.status, ReceiptExtraction.Status.FAILED)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.FAILED)
        self.assertEqual(extraction.error, run.safe_error)
