from types import SimpleNamespace

from django.test import SimpleTestCase

from documents.models import DocumentProcessingRun

from .document_receipts import _receipt_status_for_run
from .models import Expense, ReceiptExtraction


class ReceiptRetryStateTests(SimpleTestCase):
    def test_processing_run_never_regresses_visible_receipt_state_to_queued(self):
        run = SimpleNamespace(status=DocumentProcessingRun.Status.PROCESSING)

        extraction_status, expense_status = _receipt_status_for_run(run)

        self.assertEqual(extraction_status, ReceiptExtraction.Status.PROCESSING)
        self.assertEqual(expense_status, Expense.ReceiptStatus.PROCESSING)

    def test_queued_and_retry_runs_keep_the_queued_contract(self):
        for run_status in (DocumentProcessingRun.Status.QUEUED, DocumentProcessingRun.Status.RETRY):
            with self.subTest(run_status=run_status):
                run = SimpleNamespace(status=run_status)
                extraction_status, expense_status = _receipt_status_for_run(run)
                self.assertEqual(extraction_status, ReceiptExtraction.Status.QUEUED)
                self.assertEqual(expense_status, Expense.ReceiptStatus.QUEUED)
