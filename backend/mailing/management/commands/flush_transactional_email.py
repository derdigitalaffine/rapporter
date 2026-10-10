import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from mailing.service import process_one_transactional_email


class Command(BaseCommand):
    help = "Process queued FamilyOS transactional email with lease/retry semantics."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep polling for due email.")
        parser.add_argument("--interval", type=float, default=10.0, help="Seconds between empty polls in loop mode.")
        parser.add_argument("--max", type=int, default=100, help="Maximum messages processed in one non-loop run.")

    def handle(self, *args, **options):
        processed = 0
        while True:
            close_old_connections()
            try:
                did_work = process_one_transactional_email()
            finally:
                close_old_connections()
            if did_work:
                processed += 1
                if not options["loop"] and processed >= options["max"]:
                    break
                continue
            if not options["loop"]:
                break
            time.sleep(max(1.0, options["interval"]))
        if not options["loop"]:
            self.stdout.write(self.style.SUCCESS(f"Processed {processed} transactional email item(s)."))
