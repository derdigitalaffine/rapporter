from django.core.management.base import BaseCommand

from expenses.document_receipts import migrate_legacy_receipt
from expenses.models import Expense


class Command(BaseCommand):
    help = (
        "Idempotently backfill legacy Expense.receipt_content into hidden Document Core attachments. "
        "Legacy bytes are intentionally retained for rollback until a later contract migration."
    )

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=50)
        parser.add_argument("--max-items", type=int, default=0, help="Stop after N candidates (0 = unlimited).")

    def handle(self, *args, **options):
        batch_size = max(1, options["batch_size"])
        max_items = max(0, options["max_items"])
        queryset = (
            Expense.objects.filter(receipt_document__isnull=True, receipt_content__isnull=False)
            .exclude(receipt_mime="")
            .select_related("paid_by", "created_by", "receipt_document")
            .order_by("created_at", "id")
        )

        migrated = 0
        enqueued = 0
        skipped = 0
        failed = 0
        seen = 0
        for expense in queryset.iterator(chunk_size=batch_size):
            if max_items and seen >= max_items:
                break
            seen += 1
            try:
                _document, created, queued = migrate_legacy_receipt(expense)
            except Exception:
                failed += 1
                self.stderr.write(f"Receipt backfill failed for expense {expense.id}; legacy data kept intact.")
                continue
            if created:
                migrated += 1
            else:
                skipped += 1
            if queued:
                enqueued += 1

        self.stdout.write(
            f"Receipt backfill: migrated={migrated} enqueued={enqueued} skipped={skipped} failed={failed}."
        )
