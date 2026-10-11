import uuid
from importlib import import_module

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from .models import BoardPost, Family, FamilyEvent, Membership, Note, ShoppingItem, ShoppingList, Task
from .pin_adapters import adapter_key_for_post, get_pin_adapter


class PinAdapterKeyApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('stable-pin-user')
        self.family = Family.objects.create(name='Stable Pins', slug='stable-pins')
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_canonical_task_write_persists_legacy_kind_for_rollback(self):
        task = Task.objects.create(family=self.family, title='Canonical task', created_by=self.user)
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'adapter_key': 'task',
            'target_id': str(task.id),
        }, format='json')

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['adapter_key'], 'task')
        self.assertEqual(response.data['kind'], 'task')
        post = BoardPost.objects.get(pk=response.data['id'])
        self.assertEqual(post.adapter_key, 'task')
        self.assertEqual(post.kind, BoardPost.Kind.TASK)

    def test_canonical_keys_disambiguate_note_event_and_shopping_legacy_kinds(self):
        event = FamilyEvent.objects.create(family=self.family, type='family', title='Elternabend')
        note = Note.objects.create(family=self.family, author=self.user, title='Merkzettel', body='Text')
        shopping_list = ShoppingList.objects.create(family=self.family, name='Drogerie')
        item = ShoppingItem.objects.create(shopping_list=shopping_list, name='Zahnpasta')
        cases = [
            ('calendar_event', event.id, BoardPost.Kind.EVENT),
            ('note', note.id, BoardPost.Kind.NOTE_REF),
            ('shopping_item', item.id, BoardPost.Kind.SHOPPING),
        ]

        for adapter_key, target_id, expected_kind in cases:
            response = self.client.post('/api/board/', {
                'family': str(self.family.id),
                'adapter_key': adapter_key,
                'target_id': str(target_id),
            }, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data['adapter_key'], adapter_key)
            self.assertEqual(response.data['kind'], expected_kind)

        native_note = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': BoardPost.Kind.NOTE,
            'text': 'Native board note',
        }, format='json')
        self.assertEqual(native_note.status_code, 201, native_note.data)
        self.assertEqual(native_note.data['adapter_key'], '')
        self.assertEqual(native_note.data['kind'], BoardPost.Kind.NOTE)

    def test_legacy_writer_is_canonicalized_and_rolling_upgrade_row_still_resolves(self):
        task = Task.objects.create(family=self.family, title='Legacy task', created_by=self.user)
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': BoardPost.Kind.TASK,
            'target_id': str(task.id),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['adapter_key'], 'task')

        rolling = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.TASK,
            adapter_key='',
            target_id=task.id,
        )
        self.assertEqual(adapter_key_for_post(rolling), 'task')
        rows = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(rows.status_code, 200, rows.data)
        row = next(value for value in rows.data['results'] if value['id'] == str(rolling.id))
        self.assertEqual(row['target']['title'], 'Legacy task')

    def test_adapter_and_legacy_kind_mismatch_is_rejected(self):
        task = Task.objects.create(family=self.family, title='Mismatch', created_by=self.user)
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': BoardPost.Kind.TASK,
            'adapter_key': 'shopping_item',
            'target_id': str(task.id),
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('adapter_key', response.data)
        self.assertFalse(BoardPost.objects.filter(target_id=task.id).exists())

    def test_picker_accepts_canonical_and_legacy_keys_but_reports_canonical_key(self):
        FamilyEvent.objects.create(family=self.family, type='family', title='Schulfest')

        canonical = self.client.get(
            f'/api/board/picker/?family={self.family.id}&adapter_key=calendar_event&q=Schulfest'
        )
        legacy = self.client.get(
            f'/api/board/picker/?family={self.family.id}&kind=event&q=Schulfest'
        )

        for response in (canonical, legacy):
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['adapter_key'], 'calendar_event')
            self.assertEqual(response.data['kind'], 'event')
            self.assertEqual([row['title'] for row in response.data['results']], ['Schulfest'])

    def test_registry_uses_stable_issue_219_keys(self):
        for key in ('calendar_event', 'task', 'note', 'shopping_item', 'routine', 'shopping_list', 'trip', 'document'):
            self.assertIsNotNone(get_pin_adapter(key), key)
        self.assertIs(get_pin_adapter('event'), get_pin_adapter('calendar_event'))
        self.assertIs(get_pin_adapter('note_ref'), get_pin_adapter('note'))
        self.assertIs(get_pin_adapter('shopping'), get_pin_adapter('shopping_item'))


class PinAdapterKeyMigrationTests(TransactionTestCase):
    migrate_from = [('family', '0219_todo_preferences')]
    migrate_to = [('family', '0220_pinboard_adapter_keys')]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Family = old_apps.get_model('family', 'Family')
        BoardPost = old_apps.get_model('family', 'BoardPost')
        family = Family.objects.create(name='Legacy Pins', slug='legacy-pins')
        self.rows = {}
        for kind in ('event', 'task', 'note_ref', 'shopping', 'routine', 'shopping_list', 'trip', 'document'):
            row = BoardPost.objects.create(family=family, kind=kind, target_id=uuid.uuid4())
            self.rows[kind] = row.id
        self.native_note = BoardPost.objects.create(family=family, kind='note', text='Keep native').id
        self.native_photo = BoardPost.objects.create(family=family, kind='photo', text='Keep photo').id

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def assert_backfill(self):
        BoardPost = self.apps.get_model('family', 'BoardPost')
        expected = {
            'event': 'calendar_event',
            'task': 'task',
            'note_ref': 'note',
            'shopping': 'shopping_item',
            'routine': 'routine',
            'shopping_list': 'shopping_list',
            'trip': 'trip',
            'document': 'document',
        }
        for kind, adapter_key in expected.items():
            row = BoardPost.objects.get(pk=self.rows[kind])
            self.assertEqual(row.kind, kind)
            self.assertEqual(row.adapter_key, adapter_key)
        self.assertEqual(BoardPost.objects.get(pk=self.native_note).adapter_key, '')
        self.assertEqual(BoardPost.objects.get(pk=self.native_photo).adapter_key, '')

    def test_backfill_is_idempotent_and_reverse_keeps_legacy_identity(self):
        self.assert_backfill()
        migration = import_module('family.migrations.0220_pinboard_adapter_keys')
        with connection.schema_editor() as schema_editor:
            migration.backfill_pin_adapter_keys(self.apps, schema_editor)
            migration.backfill_pin_adapter_keys(self.apps, schema_editor)
        self.assert_backfill()

        BoardPost = self.apps.get_model('family', 'BoardPost')
        with connection.schema_editor() as schema_editor:
            migration.clear_pin_adapter_keys(self.apps, schema_editor)
        self.assertFalse(BoardPost.objects.exclude(adapter_key='').exists())
        self.assertEqual(BoardPost.objects.get(pk=self.rows['note_ref']).kind, 'note_ref')
        self.assertIsNotNone(BoardPost.objects.get(pk=self.rows['note_ref']).target_id)
