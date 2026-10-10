import io
import tempfile
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from documents.access import visible_documents
from documents.extraction import ExtractionResult, ProcessingError
from documents.models import Document, DocumentLink, DocumentProcessingRun
from documents.processing import claim_next_run
from documents.worker import process_claimed_run
from family.models import Family, Membership

from .models import Expense, ReceiptExtraction


class ReceiptDocumentCoreTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="receipt-owner", password="test-pass-123")
        self.other = User.objects.create_user(username="receipt-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Receipt Family", slug="receipt-family")
        self.other_family = Family.objects.create(name="Other Receipt Family", slug="other-receipt-family")
        self.member = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Receipt Owner",
        )
        self.other_member = Membership.objects.create(
            family=self.other_family,
            user=self.other,
            role=Membership.Role.OWNER,
            display_name="Outsider",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = FileSystemStorage(location=self.tmp.name)
        self.storage_patch = patch("documents.storage.default_storage", self.storage)
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.tmp.cleanup()

    def image_bytes(self, *, width=900, height=1200):
        output = io.BytesIO()
        Image.new("RGB", (width, height), "white").save(output, "PNG")
        return output.getvalue()

    def upload_receipt(self):
        upload = SimpleUploadedFile("receipt.png", self.image_bytes(), content_type="image/png")
        return self.client.post(
            "/api/expenses/receipt/",
            {"family": str(self.family.id), "receipt": upload},
            format="multipart",
        )

    def test_new_upload_uses_hidden_private_document_and_shared_queue(self):
        response = self.upload_receipt()
        self.assertEqual(response.status_code, 202, response.data)
        expense = Expense.objects.select_related("receipt_document").get(id=response.data["id"])
        extraction = ReceiptExtraction.objects.get(expense=expense)
        document = expense.receipt_document

        self.assertEqual(expense.status, Expense.Status.DRAFT)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.QUEUED)
        self.assertIsNone(expense.receipt_content)
        self.assertEqual(expense.receipt_mime, "image/webp")
        self.assertIsNotNone(document)
        self.assertEqual(document.kind, "expense_receipt")
        self.assertEqual(document.visibility, Document.Visibility.PRIVATE)
        self.assertFalse(document.library_visible)
        self.assertEqual(document.owner_membership, self.member)
        self.assertTrue(self.storage.exists(document.canonical_file))
        self.assertTrue(
            DocumentLink.objects.filter(
                document=document,
                domain_type=DocumentLink.DomainType.EXPENSE,
                object_id=expense.id,
                relationship="receipt",
            ).exists()
        )
        self.assertIsNotNone(extraction.processing_run_id)
        self.assertEqual(extraction.processing_run.status, DocumentProcessingRun.Status.QUEUED)
        self.assertFalse(visible_documents(self.user, self.family.id).filter(pk=document.pk).exists())
        self.assertTrue(
            visible_documents(self.user, self.family.id, include_domain_managed=True)
            .filter(pk=document.pk)
            .exists()
        )

    def test_shared_worker_projects_receipt_parser_into_expense_review(self):
        response = self.upload_receipt()
        expense = Expense.objects.get(id=response.data["id"])
        claimed = claim_next_run()
        result = ExtractionResult(
            text="REWE MARKT\n08.10.2026\nSUMME EUR 12,34\nGEGEBEN 20,00",
            extractor="fixture",
            quality_data={"classification": {"kind": "receipt", "confidence": 0.95}},
            fields=[],
            needs_review=True,
        )
        with patch("documents.worker.extract_document", return_value=result):
            completed = process_claimed_run(claimed)

        self.assertEqual(completed.status, DocumentProcessingRun.Status.REVIEW)
        expense.refresh_from_db()
        extraction = ReceiptExtraction.objects.get(expense=expense)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.REVIEW)
        self.assertEqual(expense.merchant, "REWE MARKT")
        self.assertEqual(expense.total_amount, Decimal("12.34"))
        self.assertEqual(extraction.status, ReceiptExtraction.Status.REVIEW)
        self.assertEqual(extraction.processing_run_id, completed.id)
        self.assertEqual(extraction.raw_text, result.text)
        self.assertEqual(extraction.total, Decimal("12.34"))
        self.assertGreater(extraction.field_confidences["total"], 0.8)

    def test_shared_worker_failure_and_retry_use_document_runs_only(self):
        response = self.upload_receipt()
        expense = Expense.objects.get(id=response.data["id"])
        first = claim_next_run()
        with patch(
            "documents.worker.extract_document",
            side_effect=ProcessingError("ocr_failed", "Lokale OCR konnte die Seite nicht verarbeiten.", retryable=False),
        ):
            failed = process_claimed_run(first)
        self.assertEqual(failed.status, DocumentProcessingRun.Status.FAILED)
        expense.refresh_from_db()
        extraction = ReceiptExtraction.objects.get(expense=expense)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.FAILED)
        self.assertEqual(extraction.status, ReceiptExtraction.Status.FAILED)

        retry = self.client.post(f"/api/expenses/{expense.id}/retry-receipt/", {}, format="json")
        self.assertEqual(retry.status_code, 202, retry.data)
        extraction.refresh_from_db()
        expense.refresh_from_db()
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.QUEUED)
        self.assertEqual(extraction.status, ReceiptExtraction.Status.QUEUED)
        self.assertNotEqual(extraction.processing_run_id, first.id)
        self.assertEqual(expense.receipt_document.processing_runs.count(), 2)

    def test_receipt_file_reads_canonical_storage_and_delete_cleans_it(self):
        response = self.upload_receipt()
        expense = Expense.objects.select_related("receipt_document").get(id=response.data["id"])
        document_id = expense.receipt_document_id
        stored_key = expense.receipt_document.canonical_file

        file_response = self.client.get(f"/api/expenses/{expense.id}/receipt-file/")
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response["Cache-Control"], "private, no-store")
        content = b"".join(file_response.streaming_content)
        with Image.open(io.BytesIO(content)) as image:
            self.assertEqual(image.format, "WEBP")

        with self.captureOnCommitCallbacks(execute=True):
            deleted = self.client.delete(f"/api/expenses/{expense.id}/receipt-file/")
        self.assertEqual(deleted.status_code, 204)
        expense.refresh_from_db()
        self.assertIsNone(expense.receipt_document_id)
        self.assertIsNone(expense.receipt_content)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.NONE)
        self.assertFalse(Document.objects.filter(pk=document_id).exists())
        self.assertFalse(self.storage.exists(stored_key))
        self.assertFalse(ReceiptExtraction.objects.filter(expense=expense).exists())

    def test_cross_family_receipt_file_stays_tenant_scoped(self):
        foreign = Expense.objects.create(
            family=self.other_family,
            title="Privat",
            total_amount="5.00",
            paid_by=self.other_member,
            created_by=self.other,
            source=Expense.Source.RECEIPT,
        )
        self.assertEqual(self.client.get(f"/api/expenses/{foreign.id}/receipt-file/").status_code, 404)

    def test_legacy_backfill_is_idempotent_and_keeps_binary_rollback_copy(self):
        raw = self.image_bytes()
        expense = Expense.objects.create(
            family=self.family,
            title="Altbeleg",
            total_amount="7.00",
            paid_by=self.member,
            created_by=self.user,
            source=Expense.Source.RECEIPT,
            status=Expense.Status.POSTED,
            receipt_status=Expense.ReceiptStatus.READY,
            receipt_content=raw,
            receipt_mime="image/png",
        )
        ReceiptExtraction.objects.create(
            expense=expense,
            status=ReceiptExtraction.Status.READY,
            merchant="ALT MARKT",
            total="7.00",
        )

        call_command("migrate_receipts_to_documents")
        expense.refresh_from_db()
        extraction = ReceiptExtraction.objects.get(expense=expense)
        first_document_id = expense.receipt_document_id
        self.assertIsNotNone(first_document_id)
        self.assertTrue(expense.receipt_content)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.READY)
        self.assertIsNone(extraction.processing_run_id)
        self.assertFalse(expense.receipt_document.library_visible)
        self.assertEqual(expense.receipt_document.processing_runs.count(), 0)

        call_command("migrate_receipts_to_documents")
        expense.refresh_from_db()
        self.assertEqual(expense.receipt_document_id, first_document_id)
        self.assertEqual(Document.objects.filter(pk=first_document_id).count(), 1)

    def test_pending_legacy_backfill_recovers_onto_shared_queue(self):
        expense = Expense.objects.create(
            family=self.family,
            paid_by=self.member,
            created_by=self.user,
            source=Expense.Source.RECEIPT,
            status=Expense.Status.DRAFT,
            receipt_status=Expense.ReceiptStatus.PROCESSING,
            receipt_content=self.image_bytes(),
            receipt_mime="image/png",
        )
        ReceiptExtraction.objects.create(expense=expense, status=ReceiptExtraction.Status.PROCESSING)

        call_command("migrate_receipts_to_documents")
        expense.refresh_from_db()
        extraction = ReceiptExtraction.objects.get(expense=expense)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.QUEUED)
        self.assertEqual(extraction.status, ReceiptExtraction.Status.QUEUED)
        self.assertIsNotNone(extraction.processing_run_id)
        self.assertEqual(extraction.processing_run.status, DocumentProcessingRun.Status.QUEUED)
