import io
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from pypdf import PdfWriter

from family.models import Family, Membership

from .extraction import ExtractionResult, ProcessingError, extract_document
from .models import Document, DocumentProcessingRun
from .processing import claim_next_run, enqueue_document, fail_run, finish_run
from .storage import canonicalize_upload, store_canonical
from .worker import process_claimed_run


class DocumentProcessingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="processor", password="test-pass-123")
        self.family = Family.objects.create(name="Processing Family", slug="processing-family")
        self.membership = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Processor",
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = FileSystemStorage(location=self.tmp.name)
        self.storage_patch = patch("documents.storage.default_storage", self.storage)
        self.storage_patch.start()

    def tearDown(self):
        self.storage_patch.stop()
        self.tmp.cleanup()

    def image_bytes(self):
        output = io.BytesIO()
        Image.new("RGB", (1000, 1400), "white").save(output, "PNG")
        return output.getvalue()

    def pdf_bytes(self, pages=1):
        output = io.BytesIO()
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=300, height=500)
        writer.write(output)
        return output.getvalue()

    def create_document(self, content=None, name="scan.png"):
        raw = content if content is not None else self.image_bytes()
        canonical = canonicalize_upload(SimpleUploadedFile(name, raw))
        document = Document(
            family=self.family,
            title="Processing fixture",
            owner_membership=self.membership,
            canonical_file="",
            mime_type=canonical.mime_type,
            size=len(canonical.content),
            sha256=canonical.sha256,
            page_count=canonical.page_count,
            created_by=self.user,
        )
        document.canonical_file = store_canonical(document.id, canonical)
        document.save(force_insert=True)
        return document

    def test_enqueue_is_idempotent_and_claim_sets_lease(self):
        document = self.create_document()
        first, created = enqueue_document(document)
        second, created_again = enqueue_document(document)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, second.id)
        self.assertEqual(document.processing_runs.count(), 1)

        claimed = claim_next_run()
        self.assertEqual(claimed.id, first.id)
        self.assertEqual(claimed.status, DocumentProcessingRun.Status.PROCESSING)
        self.assertEqual(claimed.attempts, 1)
        self.assertIsNotNone(claimed.claim_token)
        self.assertIsNotNone(claimed.started_at)
        self.assertIsNotNone(claimed.processing_started_at)
        self.assertGreater(claimed.lease_expires_at, claimed.processing_started_at)
        self.assertIsNone(claim_next_run())

    def test_expired_processing_lease_is_reclaimed_after_worker_crash(self):
        document = self.create_document()
        run, _ = enqueue_document(document)
        run.status = DocumentProcessingRun.Status.PROCESSING
        run.attempts = 1
        run.started_at = timezone.now() - timedelta(minutes=20)
        run.processing_started_at = timezone.now() - timedelta(minutes=20)
        run.lease_expires_at = timezone.now() - timedelta(minutes=10)
        run.save()

        reclaimed = claim_next_run()
        self.assertEqual(reclaimed.id, run.id)
        self.assertEqual(reclaimed.attempts, 2)
        self.assertIsNotNone(reclaimed.claim_token)
        self.assertGreater(reclaimed.lease_expires_at, timezone.now())

    def test_stale_worker_cannot_publish_after_lease_is_reclaimed(self):
        document = self.create_document()
        enqueue_document(document)
        first_claim = claim_next_run()
        first_token = first_claim.claim_token
        DocumentProcessingRun.objects.filter(pk=first_claim.pk).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )

        second_claim = claim_next_run()
        self.assertNotEqual(second_claim.claim_token, first_token)
        stale_result = ExtractionResult(
            text="stale result",
            extractor="test",
            fields=[{"key": "text.page", "value_json": {"text": "stale result"}}],
            needs_review=False,
        )
        unchanged = finish_run(first_claim, stale_result, needs_review=False)
        self.assertEqual(unchanged.status, DocumentProcessingRun.Status.PROCESSING)
        self.assertEqual(unchanged.claim_token, second_claim.claim_token)
        self.assertEqual(unchanged.normalized_text, "")
        self.assertFalse(unchanged.extracted_fields.exists())

        current_result = ExtractionResult(
            text="current result",
            extractor="test",
            fields=[{"key": "text.page", "value_json": {"text": "current result"}}],
            needs_review=False,
        )
        completed = finish_run(second_claim, current_result, needs_review=False)
        self.assertEqual(completed.status, DocumentProcessingRun.Status.READY)
        self.assertIsNone(completed.claim_token)
        self.assertEqual(completed.normalized_text, "current result")

    def test_retry_backoff_becomes_terminal_after_max_attempts(self):
        document = self.create_document()
        run, _ = enqueue_document(document)
        run.attempts = 3
        run.save(update_fields=["attempts"])
        claimed = claim_next_run()
        self.assertEqual(claimed.attempts, 4)

        failed = fail_run(
            claimed,
            error_code="ocr_failed",
            safe_error="Lokale OCR konnte die Seite nicht verarbeiten.",
            retryable=True,
        )
        self.assertEqual(failed.status, DocumentProcessingRun.Status.FAILED)
        self.assertIsNone(failed.claim_token)
        document.refresh_from_db()
        self.assertEqual(document.processing_status, Document.ProcessingStatus.FAILED)

    def test_image_ocr_persists_confidence_bounding_boxes_and_evidence(self):
        document = self.create_document()
        run, _ = enqueue_document(document)
        claimed = claim_next_run()
        tsv = {
            "text": ["Familie", "Test"],
            "conf": ["96.0", "88.0"],
            "left": [10, 90],
            "top": [20, 20],
            "width": [70, 50],
            "height": [20, 20],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        }
        with patch("documents.extraction.pytesseract.image_to_data", return_value=tsv):
            completed = process_claimed_run(claimed)

        self.assertEqual(completed.status, DocumentProcessingRun.Status.REVIEW)
        self.assertEqual(completed.normalized_text, "Familie Test")
        self.assertIsNone(completed.claim_token)
        field = completed.extracted_fields.get(key="text.page")
        self.assertEqual(field.page, 1)
        self.assertEqual(field.evidence_text, "Familie Test")
        self.assertEqual(field.bbox[:2], [0, 0])
        self.assertGreater(float(field.confidence), 0.9)
        self.assertEqual(completed.quality_data["pages"][0]["words"][0]["bbox"], [10, 20, 70, 20])

    def test_born_digital_pdf_skips_unnecessary_ocr_and_supports_multiple_pages(self):
        document = self.create_document(self.pdf_bytes(pages=2), "digital.pdf")

        class FakePage:
            images = []

            def __init__(self, text):
                self.text = text

            def extract_text(self):
                return self.text

        class FakeReader:
            def __init__(self, *args, **kwargs):
                self.pages = [
                    FakePage("Erste digitale PDF-Seite mit ausreichend eingebettetem Text."),
                    FakePage("Zweite digitale PDF-Seite mit ausreichend eingebettetem Text."),
                ]

        with patch("documents.extraction.PdfReader", FakeReader), patch("documents.extraction.pytesseract.image_to_data") as ocr:
            result = extract_document(document)

        ocr.assert_not_called()
        self.assertEqual(result.extractor, "pypdf")
        self.assertFalse(result.needs_review)
        self.assertIn("Erste digitale", result.text)
        self.assertIn("Zweite digitale", result.text)
        self.assertEqual(result.quality_data["page_count"], 2)
        self.assertFalse(result.quality_data["used_ocr"])

    def test_processing_failure_never_deletes_canonical_document(self):
        document = self.create_document()
        run, _ = enqueue_document(document)
        claimed = claim_next_run()
        stored_key = document.canonical_file
        self.assertTrue(self.storage.exists(stored_key))

        with patch(
            "documents.worker.extract_document",
            side_effect=ProcessingError("ocr_failed", "Lokale OCR fehlgeschlagen.", retryable=False),
        ):
            completed = process_claimed_run(claimed)

        self.assertEqual(completed.status, DocumentProcessingRun.Status.FAILED)
        self.assertIsNone(completed.claim_token)
        self.assertTrue(self.storage.exists(stored_key))
        self.assertEqual(Document.objects.get(pk=document.pk).canonical_file, stored_key)
