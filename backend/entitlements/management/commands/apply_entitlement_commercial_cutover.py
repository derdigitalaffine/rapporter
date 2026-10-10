from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from entitlements.services import apply_commercial_cutover


class Command(BaseCommand):
    help = "Apply the one-time entitlement commercial cutover at an explicit timestamp."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cutover-at",
            required=True,
            help="Timezone-aware ISO-8601 commercial cutover timestamp, e.g. 2026-10-10T20:00:00+02:00.",
        )

    def handle(self, *args, **options):
        raw = (options["cutover_at"] or "").strip()
        cutover_at = parse_datetime(raw)
        if cutover_at is None or timezone.is_naive(cutover_at):
            raise CommandError("--cutover-at muss ein timezone-aware ISO-8601-Zeitstempel sein.")
        try:
            marker, created_count = apply_commercial_cutover(cutover_at=cutover_at)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Commercial-Cutover {marker.key} bei {marker.cutover_at.isoformat()} angewendet: "
                f"{marker.eligible_family_count} berechtigte Familien, {created_count} neue Legacy-Grants."
            )
        )
