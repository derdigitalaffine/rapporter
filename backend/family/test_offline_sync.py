from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Family, Membership, ShoppingList, ShoppingItem, Task, TaskList, FamilyEvent, IntegrationSource
from .sync_models import SyncJournal, SyncSequence, ProcessedMutation


class OfflineSyncTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('sync', password='long-password')
        self.family = Family.objects.create(name='Sync', slug='sync')
        Membership.objects.create(user=self.user, family=self.family, role='owner')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.list = ShoppingList.objects.create(family=self.family, name='Food')
        self.item = ShoppingItem.objects.create(shopping_list=self.list, name='Milk')

    def sync(self, mutations=None, cursor=None, **kwargs):
        return self.client.post('/api/sync/', {'protocol_version': 1, 'family_id': str(self.family.id), 'cursor': cursor, 'mutations': mutations or [], **kwargs}, format='json')

    def mutation(self, **kwargs):
        return {'mutation_id': str(uuid4()), 'entity_type': 'shopping_item', 'entity_id': str(self.item.id), 'operation': 'update', 'base_version': self.item.version, 'changes': {'quantity': '2'}, **kwargs}

    def test_snapshot_scope_versions_and_no_store_http_cache(self):
        r=self.sync(); self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r['Cache-Control'],'no-store')
        self.assertEqual(r.data['snapshot']['shopping_items'][0]['version'],1)
        self.assertNotIn('items',r.data['snapshot']['shopping_lists'][0])

    def test_lost_response_retry_is_exactly_once_and_changed_key_rejected(self):
        m=self.mutation(); a=self.sync([m]); b=self.sync([m]);
        self.assertEqual(a.data['mutation_results'][0]['status'],'applied',a.data)
        self.assertEqual(b.data['mutation_results'][0]['status'],'already_applied',b.data)
        self.assertEqual(ProcessedMutation.objects.count(),1)
        m['changes']={'quantity':'3'}
        self.assertEqual(self.sync([m]).data['mutation_results'][0]['code'],'idempotency_key_reused')
        self.item.refresh_from_db(); self.assertEqual(self.item.quantity,'2')

    def test_disjoint_merge_and_true_conflict(self):
        base=self.item.version
        self.item.name='Oat milk'; self.item.save(update_fields=['name'])
        self.assertEqual(self.sync([self.mutation(base_version=base)]).data['mutation_results'][0]['status'],'applied')
        m=self.mutation(base_version=base,changes={'name':'Almond milk'})
        result=self.sync([m]).data['mutation_results'][0]
        self.assertEqual(result['status'],'conflict',result)
        self.assertEqual(result['conflicts']['name']['server'],'Oat milk')

    def test_batch_independence_and_final_client_uuid(self):
        pk=str(uuid4())
        good=self.mutation(entity_id=pk,operation='create',base_version=None,data={'shopping_list':str(self.list.id),'name':'Bread'})
        good.pop('changes')
        bad=self.mutation(changes={'hidden_from_user':self.user.id})
        results=self.sync([bad,good]).data['mutation_results']
        self.assertEqual([r['status'] for r in results],['rejected','applied'],results)
        self.assertTrue(ShoppingItem.objects.filter(pk=pk).exists())

    def test_transaction_rollback_and_bulk_writers_are_journaled(self):
        cursor=SyncSequence.objects.get(pk=1).cursor
        with self.assertRaises(RuntimeError),transaction.atomic():
            self.item.name='Rollback'; self.item.save(); raise RuntimeError()
        self.item.refresh_from_db(); self.assertEqual(self.item.name,'Milk')
        self.assertEqual(SyncSequence.objects.get(pk=1).cursor,cursor)
        ShoppingItem.objects.filter(pk=self.item.pk).update(quantity='4')
        self.item.refresh_from_db(); self.assertEqual(self.item.version,2)
        self.assertIn('quantity',SyncJournal.objects.latest('cursor').changed_fields)

    def test_deleted_entity_manifest_and_delete_edit_conflict(self):
        cursor=self.sync().data['cursor']; m=self.mutation()
        pk=str(self.item.pk); self.item.delete()
        r=self.sync(cursor=cursor)
        self.assertNotIn(pk,r.data['visibility']['shopping_item'])
        self.assertEqual(SyncJournal.objects.latest('cursor').operation,'delete')
        self.assertEqual(self.sync([m]).data['mutation_results'][0]['status'],'conflict')

    def test_cross_family_rejected_even_if_member_of_both(self):
        other=Family.objects.create(name='Other',slug='other')
        Membership.objects.create(user=self.user,family=other,role='adult')
        other_list=ShoppingList.objects.create(family=other,name='Other')
        m=self.mutation(changes={'shopping_list':str(other_list.pk)})
        self.assertEqual(self.sync([m]).data['mutation_results'][0]['status'],'rejected')
        self.item.refresh_from_db(); self.assertEqual(self.item.shopping_list_id,self.list.pk)

    def test_hidden_lists_surprises_and_revocation_manifest(self):
        from .shopping_access import set_shopping_access
        other=get_user_model().objects.create_user('other')
        Membership.objects.create(user=other,family=self.family,role='adult')
        self.client.force_authenticate(other)
        before=self.sync(); self.assertEqual(len(before.data['snapshot']['shopping_items']),1)
        set_shopping_access(self.list,actor=self.user,visibility='private',allow_initialize=True)
        after=self.sync(cursor=before.data['cursor'])
        self.assertEqual(after.data['visibility']['shopping_list'],[])
        self.assertEqual(after.data['changes'],[])
        self.assertEqual(self.sync([self.mutation()]).data['mutation_results'][0]['status'],'conflict')

    def test_protocol_and_foreign_family_fail_before_mutation(self):
        self.assertEqual(self.sync([self.mutation()],protocol_version=2).status_code,409)
        self.assertEqual(self.sync(family_id=str(uuid4())).status_code,403)
        self.assertEqual(self.sync(cursor=-1).status_code,400)

    def test_stale_cursor_snapshot(self):
        SyncSequence.objects.filter(pk=1).update(retained_after=1)
        r=self.sync(cursor=0); self.assertEqual(r.data['mode'],'snapshot')
        self.assertEqual(r.data['snapshot_cursor'],r.data['cursor'])

    def test_task_command_uses_unified_domain_and_retry(self):
        tasks=TaskList.objects.create(family=self.family,name='Tasks')
        task=Task.objects.create(family=self.family,task_list=tasks,title='Work',created_by=self.user)
        m=self.mutation(entity_type='task',entity_id=str(task.pk),base_version=task.version,operation='command',command='complete_task')
        r=self.sync([m]); self.assertEqual(r.data['mutation_results'][0]['status'],'applied',r.data)
        task.refresh_from_db(); self.assertIsNotNone(task.completed_at)
        self.assertEqual(self.sync([m]).data['mutation_results'][0]['status'],'already_applied')

    def test_external_calendar_is_read_only(self):
        source=IntegrationSource.objects.create(family=self.family,name='ICS',kind='ics')
        event=FamilyEvent.objects.create(family=self.family,source=source,type='calendar.event',title='External',starts_at=timezone.now())
        m=self.mutation(entity_type='event',entity_id=str(event.pk),base_version=event.version,changes={'title':'No'})
        result=self.sync([m]); self.assertEqual(result.data['mutation_results'][0]['code'],'read_only_source',result.data)
        self.assertTrue(result.data['snapshot']['events'][0]['read_only'])


from concurrent.futures import ThreadPoolExecutor
from threading import Event
from django.db import connection, connections
from django.test import TransactionTestCase
from unittest import skipUnless


@skipUnless(connection.vendor == 'postgresql', 'Commit-order proof requires PostgreSQL row locks')
class OfflineCommitOrderingTests(TransactionTestCase):
    def test_journal_watermark_cannot_overtake_uncommitted_writer(self):
        family=Family.objects.create(name='Concurrent',slug='concurrent')
        shopping=ShoppingList.objects.create(family=family,name='Shopping')
        item=ShoppingItem.objects.create(shopping_list=shopping,name='Milk')
        locked,release,reader_started,reader_done=Event(),Event(),Event(),Event()
        def writer():
            try:
                with transaction.atomic():
                    row=ShoppingItem.objects.get(pk=item.pk)
                    row.quantity='2';row.save(update_fields=['quantity'])
                    locked.set()
                    if not release.wait(10):raise AssertionError('writer release timeout')
            finally:connections.close_all()
        def reader():
            from .sync_tracking import sync_lock
            try:
                reader_started.set()
                with sync_lock():
                    clock=SyncSequence.objects.get(pk=1).cursor
                    row=ShoppingItem.objects.get(pk=item.pk)
                    result=(clock,row.quantity,row.version)
                reader_done.set();return result
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(writer)
            try:
                self.assertTrue(locked.wait(10))
                read=pool.submit(reader);self.assertTrue(reader_started.wait(10))
                self.assertFalse(reader_done.wait(.1),'snapshot overtook an uncommitted journal writer')
            finally:release.set()
            future.result(timeout=10)
            cursor,quantity,version=read.result(timeout=10)
        self.assertEqual(quantity,'2');self.assertEqual(version,2)
        self.assertEqual(cursor,SyncJournal.objects.latest('cursor').cursor)
