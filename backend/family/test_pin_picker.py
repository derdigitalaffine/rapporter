from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, Note, Routine, Task


class PinPickerTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('picker-owner')
        self.child = User.objects.create_user('picker-child')
        self.guest = User.objects.create_user('picker-guest')
        self.foreign_user = User.objects.create_user('picker-foreign')
        self.family = Family.objects.create(name='Picker', slug='picker')
        self.foreign = Family.objects.create(name='Foreign', slug='picker-foreign')
        Membership.objects.create(family=self.family, user=self.owner, role='owner')
        Membership.objects.create(family=self.family, user=self.child, role='child')
        Membership.objects.create(family=self.family, user=self.guest, role='guest')
        Membership.objects.create(family=self.foreign, user=self.foreign_user, role='owner')
        self.match = Task.objects.create(family=self.family, title='Turnbeutel packen', created_by=self.owner)
        Task.objects.create(family=self.family, title='Hausaufgaben', created_by=self.owner)
        self.foreign_task = Task.objects.create(family=self.foreign, title='Turnbeutel secret', created_by=self.foreign_user)
        self.private_note = Note.objects.create(family=self.family, author=self.owner, title='Privat', body='Geheim')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def url(self, **params):
        values = {'family': str(self.family.id), 'kind': 'task', **params}
        return '/api/board/picker/?' + '&'.join(f'{key}={value}' for key, value in values.items())

    def test_picker_search_is_family_scoped_and_minimal(self):
        response = self.client.get(self.url(q='Turnbeutel'))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['kind'], 'task')
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], str(self.match.id))
        self.assertEqual(response.data['results'][0]['title'], 'Turnbeutel packen')
        self.assertNotIn(str(self.foreign_task.id), str(response.data))
        self.assertNotIn('secret', str(response.data).lower())

    def test_picker_uses_current_note_visibility(self):
        self.client.force_authenticate(self.child)
        response = self.client.get(self.url(kind='note_ref'))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['results'], [])
        self.assertNotIn('Geheim', str(response.data))

    def test_picker_excludes_targets_that_cannot_be_newly_pinned(self):
        Routine.objects.create(family=self.family, name='Aktiv', active=True)
        Routine.objects.create(family=self.family, name='Archiviert', active=False)
        response = self.client.get(self.url(kind='routine'))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['title'] for row in response.data['results']], ['Aktiv'])

    def test_picker_is_paginated_and_page_size_is_bounded(self):
        for index in range(55):
            Task.objects.create(family=self.family, title=f'Task {index:02d}', created_by=self.owner)
        response = self.client.get(self.url(page_size=500))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['page_size'], 50)
        self.assertEqual(len(response.data['results']), 50)
        self.assertTrue(response.data['has_next'])

    def test_guest_foreign_family_and_unknown_kind_fail_closed(self):
        self.client.force_authenticate(self.guest)
        guest = self.client.get(self.url())
        self.assertEqual(guest.status_code, 403)

        self.client.force_authenticate(self.owner)
        foreign = self.client.get(self.url(family=str(self.foreign.id)))
        self.assertEqual(foreign.status_code, 403)
        self.assertNotIn('Turnbeutel secret', str(foreign.data))

        unknown = self.client.get(self.url(kind='not-a-real-adapter'))
        self.assertEqual(unknown.status_code, 400)
