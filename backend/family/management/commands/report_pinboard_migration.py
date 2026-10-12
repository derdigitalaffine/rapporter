import json

from django.core.management.base import BaseCommand, CommandError

from family.board_migration import migration_report, repair_legacy_adapter_keys


class Command(BaseCommand):
    help = (
        "Report the BoardPost-in-place Pinboard migration health without logging "
        "private post text, media keys, filenames, or target metadata."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--repair-adapter-keys",
            action="store_true",
            help="Idempotently fill blank canonical adapter keys from legacy kinds.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Maximum rows per repair batch (default: 500).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit one machine-readable JSON object instead of key=value lines.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1")

        before = migration_report()
        migrated = 0
        if options["repair_adapter_keys"]:
            migrated = repair_legacy_adapter_keys(batch_size=batch_size)
        report = migration_report(
            migrated=migrated,
            already_migrated=before["already_migrated"],
        )

        if options["json"]:
            self.stdout.write(json.dumps(report, sort_keys=True))
            return

        for key, value in report.items():
            self.stdout.write(f"{key}={value}")
