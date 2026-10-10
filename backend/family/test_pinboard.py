from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BoardPost, Family, Membership, Note, Task


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
        self.client = APIClient(); self.client.force_authenticate(self.owner)

    def test_reference_pin_resolves_canonical_target(self):
        response = self.client.post('/api/board/', {
            'family': str(self.family.id), 'kind': 'task', 'target_id': str(self.task.id), 'text': ''
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['kind'], 'task')
        self.assertEqual(response.data['target']['title'], 'Turnbeutel packen')
        self.assertEqual(response.data['target']['kind'], 'task')
        self.assertIn('/?page=tasks', response.data['target']['url'])

    def test_foreign_reference_is_rejected(self):
        response = self.client.post('/api/board/', {
            'family': str(self.family.id), 'kind': 'task', 'target_id': str(self.foreign_task.id)
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BoardPost.objects.filter(target_id=self.foreign_task.id).exists())

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
