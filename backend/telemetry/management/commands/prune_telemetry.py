from django.core.management.base import BaseCommand

from telemetry.service import prune_raw_events


class Command(BaseCommand):
    help = "Delete expired raw telemetry/audit events in bounded batches."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, *args, **options):
        result = prune_raw_events(batch_size=options["batch_size"])
        self.stdout.write(
            self.style.SUCCESS(
                "telemetry prune: "
                f"usage={result['usage_deleted']} audit={result['audit_deleted']}"
            )
        )
