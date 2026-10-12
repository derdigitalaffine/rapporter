from django.contrib.auth import get_user_model
from datetime import date
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from documents.models import Document, DocumentAccess
from .models import Family, FamilyEvent, Membership, Note, NoteShare, Routine, ShoppingItem, ShoppingList, Task, Trip
from .pin_adapters import get_pin_adapter
from .pin_picker_views import MAX_OFFSET


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

    def test_task_query_budget_is_constant_and_previews_only_page(self):
        Task.objects.filter(family=self.family).delete()
        adapter = get_pin_adapter('task')
        for count in (1, 20, 50):
            with self.subTest(count=count):
                Task.objects.filter(family=self.family).delete()
                Task.objects.bulk_create([
                    Task(family=self.family, title=f'Task {index}', created_by=self.owner)
                    for index in range(count + 1)
                ])
                with patch.object(adapter, 'preview', wraps=adapter.preview) as preview:
                    with CaptureQueriesContext(connection) as captured:
                        response = self.client.get(self.url(page_size=count))
                    self.assertEqual(response.status_code, 200, response.data)
                    self.assertEqual(len(response.data['results']), count)
                    self.assertTrue(response.data['has_next'])
                    self.assertEqual(preview.call_count, count)
                    self.assertEqual(len(captured), 2, [q['sql'] for q in captured])

    def test_lifecycle_filter_precedes_pagination_and_single_admission_agrees(self):
        active = [Routine.objects.create(family=self.family, name=f'Active {index}') for index in range(5)]
        for index in range(30):
            Routine.objects.create(family=self.family, name=f'Inactive {index}', active=False)
        adapter = get_pin_adapter('routine')
        expected = list(adapter.pinnable_queryset(self.owner, self.family.id).order_by('-updated_at', '-id').values_list('id', flat=True))
        seen = []
        for page in (1, 2, 3):
            response = self.client.get(self.url(kind='routine', page=page, page_size=2))
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['has_next'], page < 3)
            seen.extend(row['id'] for row in response.data['results'])
        self.assertEqual(seen, [str(pk) for pk in expected])
        archived = Routine.objects.filter(active=False).first()
        self.assertFalse(adapter.can_pin(self.owner, self.family.id, archived.id))
        self.assertTrue(adapter.can_view(self.owner, self.family.id, archived.id))
        self.assertTrue(adapter.can_pin(self.owner, self.family.id, active[0].id))

    def test_canonical_source_groups_and_private_gift_visibility(self):
        event = FamilyEvent.objects.create(family=self.family, type='family', title='Event')
        NoteShare.objects.create(note=self.private_note, user=self.child, permission='read')
        shopping = ShoppingList.objects.create(family=self.family, name='List')
        item = ShoppingItem.objects.create(shopping_list=shopping, name='Item')
        gift = ShoppingItem.objects.create(shopping_list=shopping, name='Secret gift', hidden_from_user=self.child)
        trip = Trip.objects.create(family=self.family, title='Trip', destination='Berlin', starts_on=date(2027, 1, 1), ends_on=date(2027, 1, 2), created_by=self.owner)
        self.client.force_authenticate(self.child)
        for key, target in [('calendar_event', event), ('note', self.private_note), ('shopping_item', item), ('shopping_list', shopping), ('trip', trip)]:
            with self.subTest(key=key):
                adapter = get_pin_adapter(key)
                response = self.client.get(self.url(adapter_key=key))
                self.assertEqual(response.status_code, 200, response.data)
                self.assertIn(str(target.id), [row['id'] for row in response.data['results']])
                self.assertTrue(adapter.can_pin(self.child, self.family.id, target.id))
                self.assertFalse(adapter.can_pin(self.child, self.foreign.id, target.id))
                self.assertNotIn(str(gift.id), str(response.data))
        self.assertFalse(get_pin_adapter('shopping_item').can_pin(self.child, self.family.id, gift.id))
        shopping.archived = True
        shopping.save(update_fields=['archived'])
        response = self.client.get(self.url(adapter_key='shopping_list'))
        self.assertEqual(response.data['results'], [])
        self.assertFalse(get_pin_adapter('shopping_list').can_pin(self.child, self.family.id, shopping.id))
        self.assertTrue(get_pin_adapter('shopping_list').can_view(self.child, self.family.id, shopping.id))

    def test_document_picker_reuses_current_acl_and_archived_read_lifecycle(self):
        owner_membership = Membership.objects.get(user=self.owner, family=self.family)
        child_membership = Membership.objects.get(user=self.child, family=self.family)
        document = Document.objects.create(family=self.family, title='Selected document', visibility=Document.Visibility.SELECTED, owner_membership=owner_membership, canonical_file='documents/test.pdf', mime_type='application/pdf', size=1, sha256='a' * 64, created_by=self.owner)
        adapter = get_pin_adapter('document')
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get(self.url(adapter_key='document')).data['results'], [])
        access = DocumentAccess.objects.create(document=document, membership=child_membership, can_view=True)
        self.assertTrue(adapter.can_pin(self.child, self.family.id, document.id))
        self.assertEqual(self.client.get(self.url(adapter_key='document')).data['results'][0]['id'], str(document.id))
        document.archived_at = timezone.now()
        document.save(update_fields=['archived_at'])
        self.assertEqual(self.client.get(self.url(adapter_key='document')).data['results'], [])
        self.assertFalse(adapter.can_pin(self.child, self.family.id, document.id))
        self.assertTrue(adapter.can_view(self.child, self.family.id, document.id))
        access.delete()
        self.assertFalse(adapter.can_view(self.child, self.family.id, document.id))

    def test_invalid_family_and_page_bounds_are_controlled_without_source_reads(self):
        for params in ({'family': 'not-a-uuid'}, {'page': 'x'}, {'page': '0'}, {'page': '-1'}, {'page_size': 'x'}, {'page_size': '0'}, {'page': str(MAX_OFFSET + 2), 'page_size': 1}):
            with self.subTest(params=params), CaptureQueriesContext(connection) as captured:
                response = self.client.get(self.url(**params))
                self.assertEqual(response.status_code, 400, response.data)
                self.assertLessEqual(len(captured), 1)
        boundary = self.client.get(self.url(page=MAX_OFFSET + 1, page_size=1))
        self.assertEqual(boundary.status_code, 200, boundary.data)
        self.assertEqual(boundary.data['results'], [])
        self.assertFalse(boundary.data['has_next'])

    def test_unauthenticated_suspended_and_superadmin_without_membership_are_denied(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url()).status_code, (401, 403))
        self.client.force_authenticate(self.owner)
        self.family.status = Family.Status.SUSPENDED
        self.family.save(update_fields=['status'])
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.family.status = Family.Status.ACTIVE
        self.family.save(update_fields=['status'])
        self.foreign_user.is_superuser = True
        self.foreign_user.save(update_fields=['is_superuser'])
        self.client.force_authenticate(self.foreign_user)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
