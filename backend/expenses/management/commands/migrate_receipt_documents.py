from django.core.management.base import BaseCommand

from expenses.models import Expense
from expenses.receipt_documents import migrate_legacy_receipt


class Command(BaseCommand):
    help = "Idempotently attach legacy Expense.receipt_content rows to the shared Document core."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Maximum rows to migrate in this invocation (0 = all).")

    def handle(self, *args, **options):
        queryset = (
            Expense.objects.filter(receipt_document__isnull=True, receipt_content__isnull=False)
            .select_related("family", "paid_by", "created_by")
            .order_by("created_at")
        )
        limit = max(0, options["limit"])
        if limit:
            queryset = queryset[:limit]

        migrated = 0
        skipped = 0
        failed = 0
        rows = queryset if limit else queryset.iterator()
        for expense in rows:
            try:
                document, _ = migrate_legacy_receipt(expense)
            except (ValueError, RuntimeError, OSError):
                # Per-row migration failures must not abort the remaining
                # rollback-safe backfill. The command intentionally emits counts
                # only, never raw paths/content or OCR text.
                failed += 1
                continue
            if document:
                migrated += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Legacy receipt migration complete: migrated={migrated} skipped={skipped} failed={failed}"
            )
        )
