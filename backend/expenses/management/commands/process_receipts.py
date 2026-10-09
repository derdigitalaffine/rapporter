import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from expenses.models import Expense, ReceiptExtraction
from expenses.ocr import process_receipt_extraction


class Command(BaseCommand):
    help = "Process queued receipt OCR jobs and clean abandoned drafts."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep polling for queued receipt jobs.")
        parser.add_argument("--sleep", type=float, default=2.0, help="Polling interval in seconds when --loop is used.")

    def handle(self, *args, **options):
        while True:
            now = timezone.now()
            ReceiptExtraction.objects.filter(
                status=ReceiptExtraction.Status.PROCESSING,
                updated_at__lt=now - timedelta(minutes=10),
            ).update(status=ReceiptExtraction.Status.QUEUED, error="")
            Expense.objects.filter(
                status=Expense.Status.DRAFT,
                created_at__lt=now - timedelta(hours=24),
            ).delete()
            ids = list(
                ReceiptExtraction.objects.filter(status=ReceiptExtraction.Status.QUEUED)
                .order_by("created_at")
                .values_list("id", flat=True)[:10]
            )
            for extraction_id in ids:
                process_receipt_extraction(extraction_id)
            if not options["loop"]:
                break
            if not ids:
                time.sleep(max(0.25, options["sleep"]))
