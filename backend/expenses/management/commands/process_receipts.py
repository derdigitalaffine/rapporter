import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from expenses.models import Expense
from pets.models import PetDocument
from pets.ocr import process_pet_document


class Command(BaseCommand):
    help = (
        "Deprecated compatibility loop for private pet-document OCR plus abandoned Expense draft cleanup. "
        "Receipt OCR is handled exclusively by process_documents."
    )

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep polling for legacy pet OCR jobs.")
        parser.add_argument("--sleep", type=float, default=2.0, help="Polling interval in seconds when --loop is used.")

    def handle(self, *args, **options):
        while True:
            now = timezone.now()
            PetDocument.objects.filter(
                extraction_status=PetDocument.ExtractionStatus.PROCESSING,
                updated_at__lt=now - timedelta(minutes=10),
            ).update(extraction_status=PetDocument.ExtractionStatus.QUEUED, extraction_error="", updated_at=now)
            Expense.objects.filter(
                status=Expense.Status.DRAFT,
                created_at__lt=now - timedelta(hours=24),
            ).delete()
            pet_document_ids = list(
                PetDocument.objects.filter(extraction_status=PetDocument.ExtractionStatus.QUEUED)
                .order_by("created_at")
                .values_list("id", flat=True)[:10]
            )
            for document_id in pet_document_ids:
                try:
                    process_pet_document(document_id)
                except Exception:
                    self.stderr.write("Pet document OCR job failed unexpectedly; continuing worker loop.")
            if not options["loop"]:
                break
            if not pet_document_ids:
                time.sleep(max(0.25, options["sleep"]))
