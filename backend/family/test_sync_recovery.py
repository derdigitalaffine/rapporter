from datetime import timedelta
from io import StringIO

from django.core.management import call_command, CommandError
from django.utils import timezone

from .sync_models import SyncJournal, SyncSequence, ProcessedMutation
from django.test import TestCase
from . import test_offline_sync as fixtures


class OfflineRetentionTests(TestCase):
    setUp = fixtures.OfflineSyncTests.setUp
    sync = fixtures.OfflineSyncTests.sync
    mutation = fixtures.OfflineSyncTests.mutation
    def test_pruning_is_dry_run_safe_idempotent_and_resets_stale_clients(self):
        mutation = self.mutation()
        self.assertEqual(self.sync([mutation]).data['mutation_results'][0]['status'], 'applied')
        last = SyncSequence.objects.get(pk=1).cursor
        SyncJournal.objects.update(created_at=timezone.now() - timedelta(days=91))
        count = SyncJournal.objects.count()
        call_command('prune_sync_journal', dry_run=True, stdout=StringIO())
        self.assertEqual(SyncJournal.objects.count(), count)
        self.assertEqual(SyncSequence.objects.get(pk=1).retained_after, 0)
        call_command('prune_sync_journal', stdout=StringIO())
        self.assertEqual(SyncJournal.objects.count(), 0)
        self.assertEqual(SyncSequence.objects.get(pk=1).retained_after, last)
        self.assertEqual(self.sync(cursor=0).data['mode'], 'snapshot')
        self.assertEqual(self.sync([mutation], cursor=0).data['mutation_results'][0]['status'], 'already_applied')
        self.assertEqual(ProcessedMutation.objects.count(), 1)
        call_command('prune_sync_journal', stdout=StringIO())
        self.assertEqual(SyncSequence.objects.get(pk=1).retained_after, last)

    def test_recent_rows_survive_and_short_retention_is_rejected(self):
        with self.assertRaises(CommandError):
            call_command('prune_sync_journal', days=89, stdout=StringIO())
        oldest = SyncJournal.objects.order_by('cursor').first()
        SyncJournal.objects.filter(pk=oldest.pk).update(created_at=timezone.now() - timedelta(days=91))
        recent = set(SyncJournal.objects.exclude(pk=oldest.pk).values_list('pk', flat=True))
        call_command('prune_sync_journal', stdout=StringIO())
        self.assertEqual(set(SyncJournal.objects.values_list('pk', flat=True)), recent)

    def test_clock_reversal_does_not_remove_a_recent_middle_entry(self):
        self.item.quantity = '4'
        self.item.save()
        rows = list(SyncJournal.objects.order_by('cursor'))
        SyncJournal.objects.filter(pk__in=[rows[0].pk, rows[-1].pk]).update(created_at=timezone.now() - timedelta(days=92))
        call_command('prune_sync_journal', stdout=StringIO())
        self.assertTrue(SyncJournal.objects.filter(pk=rows[1].pk).exists())
        self.assertTrue(SyncJournal.objects.filter(pk=rows[-1].pk).exists())
