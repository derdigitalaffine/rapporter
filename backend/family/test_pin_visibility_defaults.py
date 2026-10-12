from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BoardPost, Family, Membership, Note, NoteShare, Task


class PinVisibilityDefaultTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('pin-default-owner')
        self.selected = User.objects.create_user('pin-default-selected')
        self.other = User.objects.create_user('pin-default-other')
        self.family = Family.objects.create(name='Pin defaults', slug='pin-defaults')
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role='owner')
        self.selected_membership = Membership.objects.create(family=self.family, user=self.selected, role='child')
        Membership.objects.create(family=self.family, user=self.other, role='adult')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _rows(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results']

    def test_private_note_reference_inherits_private_when_visibility_is_omitted(self):
        note = Note.objects.create(
            family=self.family,
            author=self.owner,
            title='Private source',
            body='Only owner',
        )
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'note_ref',
            'target_id': str(note.id),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['visibility'], BoardPost.Visibility.PRIVATE)
        self.assertEqual(response.data['effective_scope'], BoardPost.Visibility.PRIVATE)
        self.assertEqual(self._rows(self.selected), [])
        self.assertEqual(self._rows(self.other), [])

    def test_selected_note_reference_inherits_selected_memberships(self):
        note = Note.objects.create(
            family=self.family,
            author=self.owner,
            title='Selected source',
            body='Owner and selected',
        )
        NoteShare.objects.create(note=note, user=self.selected, permission='read')
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'note_ref',
            'target_id': str(note.id),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['visibility'], BoardPost.Visibility.SELECTED)
        self.assertEqual(response.data['effective_scope'], BoardPost.Visibility.SELECTED)
        self.assertEqual(response.data['selected_membership_ids'], [str(self.selected_membership.id)])
        selected_rows = self._rows(self.selected)
        self.assertEqual(len(selected_rows), 1)
        self.assertEqual(selected_rows[0]['effective_scope'], BoardPost.Visibility.SELECTED)
        self.assertEqual(self._rows(self.other), [])

    def test_family_task_reference_inherits_family(self):
        task = Task.objects.create(
            family=self.family,
            title='Family source',
            created_by=self.owner,
        )
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'task',
            'target_id': str(task.id),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['visibility'], BoardPost.Visibility.FAMILY)
        self.assertEqual(response.data['effective_scope'], BoardPost.Visibility.FAMILY)
        self.assertEqual(len(self._rows(self.selected)), 1)
        self.assertEqual(len(self._rows(self.other)), 1)
