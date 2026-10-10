import io
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from documents.extraction import ExtractionResult
from documents.models import DocumentProcessingRun
from documents.processing import claim_next_run
from documents.worker import process_claimed_run
from family.models import Family, Membership

from .models import Expense, ReceiptExtraction


class ReceiptDeleteRaceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="receipt-delete-race", password="test-pass-123")
        self.family = Family.objects.create(name="Receipt Delete Family", slug="receipt-delete-family")
        Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Receipt Delete",
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

    def test_deleted_claimed_receipt_becomes_clean_claim_loss_not_worker_crash(self):
        output = io.BytesIO()
        Image.new("RGB", (900, 1200), "white").save(output, "PNG")
        uploaded = self.client.post(
            "/api/expenses/receipt/",
            {
                "family": str(self.family.id),
                "receipt": SimpleUploadedFile("receipt.png", output.getvalue(), content_type="image/png"),
            },
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, 202, uploaded.data)
        expense = Expense.objects.select_related("receipt_document").get(id=uploaded.data["id"])
        stored_key = expense.receipt_document.canonical_file
        claimed = claim_next_run()
        self.assertIsNotNone(claimed)
        self.assertTrue(DocumentProcessingRun.objects.filter(pk=claimed.pk).exists())

        with self.captureOnCommitCallbacks(execute=True):
            deleted = self.client.delete(f"/api/expenses/{expense.id}/receipt-file/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(DocumentProcessingRun.objects.filter(pk=claimed.pk).exists())
        self.assertFalse(self.storage.exists(stored_key))

        extracted = ExtractionResult(text="stale", extractor="fixture", fields=[], needs_review=True)
        with patch("documents.worker.extract_document", return_value=extracted):
            result = process_claimed_run(claimed)
        self.assertIsNone(result)

        expense.refresh_from_db()
        self.assertIsNone(expense.receipt_document_id)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.NONE)
        self.assertFalse(ReceiptExtraction.objects.filter(expense=expense).exists())
