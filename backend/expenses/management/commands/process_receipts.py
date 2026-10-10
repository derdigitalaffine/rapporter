import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from expenses.models import Expense, ReceiptExtraction
from expenses.ocr import process_receipt_extraction
from pets.models import PetDocument
from pets.ocr import process_pet_document


class Command(BaseCommand):
    help = "Process queued receipt and private pet-document OCR jobs and clean abandoned drafts."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep polling for queued OCR jobs.")
        parser.add_argument("--sleep", type=float, default=2.0, help="Polling interval in seconds when --loop is used.")

    def handle(self, *args, **options):
        while True:
            now = timezone.now()
            ReceiptExtraction.objects.filter(
                status=ReceiptExtraction.Status.PROCESSING,
                updated_at__lt=now - timedelta(minutes=10),
            ).update(status=ReceiptExtraction.Status.QUEUED, error="", updated_at=now)
            PetDocument.objects.filter(
                extraction_status=PetDocument.ExtractionStatus.PROCESSING,
                updated_at__lt=now - timedelta(minutes=10),
            ).update(extraction_status=PetDocument.ExtractionStatus.QUEUED, extraction_error="", updated_at=now)
            Expense.objects.filter(
                status=Expense.Status.DRAFT,
                created_at__lt=now - timedelta(hours=24),
            ).delete()
            receipt_ids = list(
                ReceiptExtraction.objects.filter(status=ReceiptExtraction.Status.QUEUED)
                .order_by("created_at")
                .values_list("id", flat=True)[:10]
            )
            pet_document_ids = list(
                PetDocument.objects.filter(extraction_status=PetDocument.ExtractionStatus.QUEUED)
                .order_by("created_at")
                .values_list("id", flat=True)[:10]
            )
            for extraction_id in receipt_ids:
                try:
                    process_receipt_extraction(extraction_id)
                except Exception:
                    self.stderr.write("Receipt OCR job failed unexpectedly; continuing worker loop.")
            for document_id in pet_document_ids:
                try:
                    process_pet_document(document_id)
                except Exception:
                    self.stderr.write("Pet document OCR job failed unexpectedly; continuing worker loop.")
            if not options["loop"]:
                break
            if not receipt_ids and not pet_document_ids:
                time.sleep(max(0.25, options["sleep"]))
