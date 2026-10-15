"""Prune only an old, committed journal prefix; never prune idempotency receipts."""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max, Min
from django.utils import timezone

from family.sync_models import SyncJournal, SyncSequence
from family.sync_tracking import sync_lock


class Command(BaseCommand):
    help = 'Prune sync journal history older than at least 90 days; stale clients recover by snapshot.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=90)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if options['days'] < 90:
            raise CommandError('Journal retention cannot be shorter than 90 days.')
        cutoff = timezone.now() - timedelta(days=options['days'])
        with sync_lock():
            clock = SyncSequence.objects.get(pk=1)
            old = SyncJournal.objects.filter(created_at__lt=cutoff)
            boundary = old.aggregate(value=Max('cursor'))['value']
            if boundary is None:
                self.stdout.write('No expired journal prefix.')
                return
            # Clock corrections must not cause a recent row to be removed merely
            # because an older timestamp appeared at a later cursor.
            recent = SyncJournal.objects.filter(created_at__gte=cutoff).aggregate(value=Min('cursor'))['value']
            if recent is not None:
                boundary = min(boundary, recent - 1)
            boundary = min(boundary, clock.cursor)
            rows = SyncJournal.objects.filter(cursor__lte=boundary, created_at__lt=cutoff)
            count = rows.count()
            if not options['dry_run'] and boundary > clock.retained_after:
                rows.delete()
                clock.retained_after = boundary
                clock.save(update_fields=['retained_after'])
            self.stdout.write(f"{'Would prune' if options['dry_run'] else 'Pruned'} {count} rows; retained_after={max(clock.retained_after, boundary)}")
