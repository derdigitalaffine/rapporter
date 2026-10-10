import io
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from documents.processing import claim_next_run
from family.models import Family, Membership

from .models import Expense, ReceiptExtraction


class ReceiptRetryRaceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="receipt-race", password="test-pass-123")
        self.family = Family.objects.create(name="Receipt Race Family", slug="receipt-race-family")
        Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Receipt Race",
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

    def test_retry_during_active_ocr_does_not_move_state_back_to_queued(self):
        output = io.BytesIO()
        Image.new("RGB", (900, 1200), "white").save(output, "PNG")
        response = self.client.post(
            "/api/expenses/receipt/",
            {
                "family": str(self.family.id),
                "receipt": SimpleUploadedFile("receipt.png", output.getvalue(), content_type="image/png"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 202, response.data)
        expense = Expense.objects.get(id=response.data["id"])

        claimed = claim_next_run()
        self.assertIsNotNone(claimed)
        expense.refresh_from_db()
        extraction = ReceiptExtraction.objects.get(expense=expense)
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.PROCESSING)
        self.assertEqual(extraction.status, ReceiptExtraction.Status.PROCESSING)
        self.assertEqual(extraction.processing_run_id, claimed.id)

        retry = self.client.post(f"/api/expenses/{expense.id}/retry-receipt/", {}, format="json")
        self.assertEqual(retry.status_code, 202, retry.data)
        expense.refresh_from_db()
        extraction.refresh_from_db()
        self.assertEqual(expense.receipt_status, Expense.ReceiptStatus.PROCESSING)
        self.assertEqual(extraction.status, ReceiptExtraction.Status.PROCESSING)
        self.assertEqual(extraction.processing_run_id, claimed.id)
        self.assertEqual(expense.receipt_document.processing_runs.count(), 1)
