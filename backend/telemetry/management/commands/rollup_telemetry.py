from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from telemetry.service import recompute_daily_rollups


class Command(BaseCommand):
    help = "Recompute deterministic UTC daily telemetry rollups."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="day", help="UTC day in YYYY-MM-DD; defaults to yesterday.")

    def handle(self, *args, **options):
        raw = options.get("day")
        if raw:
            try:
                day = date.fromisoformat(raw)
            except ValueError as exc:
                raise CommandError("--date must be YYYY-MM-DD") from exc
        else:
            day = timezone.now().date() - timedelta(days=1)
        rows = recompute_daily_rollups(day)
        self.stdout.write(self.style.SUCCESS(f"telemetry rollup {day.isoformat()}: {len(rows)} rows"))
