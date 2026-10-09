import time
from django.db import close_old_connections
from django.core.management.base import BaseCommand, CommandError
from family.notification_digests import flush_notification_batches

class Command(BaseCommand):
    help = "Deliver due notification summaries independently of integration polling"
    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=30)
    def handle(self, *args, **options):
        interval = options["interval"]
        if not 10 <= interval <= 300:
            raise CommandError("--interval must be between 10 and 300 seconds")
        while True:
            close_old_connections()
            try:
                result = flush_notification_batches()
                if result["sent"] or result["errors"] or not options["loop"]:
                    self.stdout.write(str(result))
            except Exception as exc:
                self.stderr.write(f"Notification delivery failed: {exc}")
                if not options["loop"]: raise
            finally:
                close_old_connections()
            if not options["loop"]: return
            time.sleep(interval)
