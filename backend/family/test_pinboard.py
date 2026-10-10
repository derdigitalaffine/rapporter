import uuid

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .models import (
    BoardPost,
    Family,
    FamilyEvent,
    Membership,
    Note,
    NoteShare,
    ShoppingItem,
    ShoppingList,
    Task,
)


class PinboardReferenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('pin-owner')
        self.child = User.objects.create_user('pin-child')
        self.guest = User.objects.create_user('pin-guest')
        self.foreign_user = User.objects.create_user('pin-foreign')
        self.family = Family.objects.create(name='Pins', slug='pins')
        self.foreign = Family.objects.create(name='Other Pins', slug='other-pins')
        Membership.objects.create(family=self.family, user=self.owner, role='owner')
        Membership.objects.create(family=self.family, user=self.child, role='child')
        Membership.objects.create(family=self.family, user=self.guest, role='guest')
        Membership.objects.create(family=self.foreign, user=self.foreign_user, role='owner')
        self.task = Task.objects.create(family=self.family, title='Turnbeutel packen', created_by=self.owner)
        self.foreign_task = Task.objects.create(family=self.foreign, title='Foreign secret', created_by=self.foreign_user)
        self.note = Note.objects.create(family=self.family, author=self.owner, title='Privat', body='Nur für mich')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_reference_pin_resolves_canonical_target(self):
        response = self.client.post('/api/board/', {
            'family': str(self.family.id), 'kind': 'task', 'target_id': str(self.task.id), 'text': ''
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['kind'], 'task')
        self.assertEqual(response.data['target']['title'], 'Turnbeutel packen')
        self.assertEqual(response.data['target']['kind'], 'task')
        self.assertIn('/?page=tasks', response.data['target']['url'])

    def test_existing_event_note_and_shopping_adapters_resolve(self):
        event = FamilyEvent.objects.create(family=self.family, type='family', title='Elternabend')
        shopping_list = ShoppingList.objects.create(family=self.family, name='Drogerie')
        item = ShoppingItem.objects.create(shopping_list=shopping_list, name='Zahnpasta')
        NoteShare.objects.create(note=self.note, user=self.child, permission='read')
        pins = [
            BoardPost.objects.create(family=self.family, author=self.owner, kind='event', target_id=event.id),
            BoardPost.objects.create(family=self.family, author=self.owner, kind='note_ref', target_id=self.note.id),
            BoardPost.objects.create(family=self.family, author=self.owner, kind='shopping', target_id=item.id),
        ]
        response = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(response.status_code, 200, response.data)
        targets = {row['id']: row['target'] for row in response.data['results']}
        self.assertEqual(targets[str(pins[0].id)]['title'], 'Elternabend')
        self.assertEqual(targets[str(pins[1].id)]['title'], 'Privat')
        self.assertEqual(targets[str(pins[2].id)]['title'], 'Zahnpasta')
        self.assertEqual(targets[str(pins[2].id)]['subtitle'], 'Drogerie')

    def test_foreign_reference_is_rejected(self):
        response = self.client.post('/api/board/', {
            'family': str(self.family.id), 'kind': 'task', 'target_id': str(self.foreign_task.id)
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BoardPost.objects.filter(target_id=self.foreign_task.id).exists())

    def test_foreign_family_cannot_be_used_as_target_existence_oracle(self):
        existing = self.client.post('/api/board/', {
            'family': str(self.foreign.id), 'kind': 'task', 'target_id': str(self.foreign_task.id)
        }, format='json')
        missing = self.client.post('/api/board/', {
            'family': str(self.foreign.id), 'kind': 'task', 'target_id': str(uuid.uuid4())
        }, format='json')
        self.assertEqual(existing.status_code, 403)
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(existing.data, missing.data)
        self.assertFalse(BoardPost.objects.filter(family=self.foreign, author=self.owner).exists())

    def test_pin_does_not_grant_access_to_private_note(self):
        created = self.client.post('/api/board/', {
            'family': str(self.family.id), 'kind': 'note_ref', 'target_id': str(self.note.id)
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['target']['title'], 'Privat')
        self.client.force_authenticate(self.child)
        row = self.client.get(f'/api/board/?family={self.family.id}').data['results'][0]
        self.assertEqual(row['kind'], 'note_ref')
        self.assertEqual(row['target'], {'id': str(self.note.id), 'kind': 'note_ref', 'available': False})
        self.assertNotIn('Nur für mich', str(row))
        self.assertNotIn('Privat', str(row))

    def test_revoked_note_share_is_reauthorized_on_each_read(self):
        share = NoteShare.objects.create(note=self.note, user=self.child, permission='read')
        BoardPost.objects.create(family=self.family, author=self.owner, kind='note_ref', target_id=self.note.id)
        self.client.force_authenticate(self.child)
        visible = self.client.get(f'/api/board/?family={self.family.id}').data['results'][0]
        self.assertEqual(visible['target']['title'], 'Privat')
        share.delete()
        hidden = self.client.get(f'/api/board/?family={self.family.id}').data['results'][0]
        self.assertEqual(hidden['target'], {'id': str(self.note.id), 'kind': 'note_ref', 'available': False})
        self.assertNotIn('Privat', str(hidden))
        self.assertNotIn('Nur für mich', str(hidden))

    def test_hidden_shopping_item_never_leaks_through_pin(self):
        shopping_list = ShoppingList.objects.create(family=self.family, name='Geschenke')
        item = ShoppingItem.objects.create(
            shopping_list=shopping_list,
            name='Geheimes Geschenk',
            hidden_from_user=self.child,
        )
        BoardPost.objects.create(family=self.family, author=self.owner, kind='shopping', target_id=item.id)
        self.client.force_authenticate(self.child)
        row = self.client.get(f'/api/board/?family={self.family.id}').data['results'][0]
        self.assertEqual(row['target'], {'id': str(item.id), 'kind': 'shopping', 'available': False})
        self.assertNotIn('Geheimes Geschenk', str(row))
        self.assertNotIn('Geschenke', str(row))

    def test_deleted_target_has_neutral_unavailable_lifecycle(self):
        target_id = self.task.id
        pin = BoardPost.objects.create(family=self.family, author=self.owner, kind='task', target_id=target_id)
        self.task.delete()
        row = self.client.get(f'/api/board/?family={self.family.id}').data['results'][0]
        self.assertEqual(row['id'], str(pin.id))
        self.assertEqual(row['target'], {'id': str(target_id), 'kind': 'task', 'available': False})
        self.assertNotIn('Turnbeutel packen', str(row))

    def test_board_page_batches_target_queries_per_adapter(self):
        tasks = [
            Task.objects.create(family=self.family, title=f'Task {index}', created_by=self.owner)
            for index in range(8)
        ]
        BoardPost.objects.bulk_create([
            BoardPost(family=self.family, author=self.owner, kind='task', target_id=task.id, position=index)
            for index, task in enumerate(tasks)
        ])
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(response.status_code, 200, response.data)
        task_queries = [query['sql'] for query in captured if 'family_task' in query['sql'].lower()]
        self.assertEqual(len(task_queries), 1, task_queries)
        self.assertEqual(
            {row['target']['title'] for row in response.data['results']},
            {task.title for task in tasks},
        )

    def test_non_reference_kind_rejects_target_id(self):
        response = self.client.post('/api/board/', {
            'family': str(self.family.id), 'kind': 'note', 'target_id': str(self.task.id), 'text': 'No generic refs'
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BoardPost.objects.filter(text='No generic refs').exists())

    def test_reorder_is_family_scoped_and_persistent(self):
        rows = [BoardPost.objects.create(family=self.family, author=self.owner, text=f'Pin {i}', position=i * 1000) for i in range(3)]
        response = self.client.post('/api/board/reorder/', {
            'family': str(self.family.id), 'ids': [str(rows[2].id), str(rows[0].id), str(rows[1].id)]
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(BoardPost.objects.filter(family=self.family).values_list('id', flat=True)), [rows[2].id, rows[0].id, rows[1].id])
        response = self.client.post('/api/board/reorder/', {
            'family': str(self.family.id), 'ids': [str(rows[0].id), str(BoardPost.objects.create(family=self.foreign, author=self.foreign_user, text='Other').id)]
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_guest_cannot_create_or_reorder(self):
        row = BoardPost.objects.create(family=self.family, author=self.owner, text='Pinned')
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.client.post('/api/board/', {'family': str(self.family.id), 'text': 'no'}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/board/reorder/', {'family': str(self.family.id), 'ids': [str(row.id)]}, format='json').status_code, 403)

    def test_reference_identity_cannot_be_swapped_on_patch(self):
        created = self.client.post('/api/board/', {
            'family': str(self.family.id), 'kind': 'task', 'target_id': str(self.task.id)
        }, format='json')
        self.assertEqual(created.status_code, 201)
        response = self.client.patch(f"/api/board/{created.data['id']}/", {'target_id': str(self.foreign_task.id)}, format='json')
        self.assertEqual(response.status_code, 400)
