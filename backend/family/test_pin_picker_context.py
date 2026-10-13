import uuid
from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from documents.models import Document, DocumentAccess
from .models import BoardPost, Family, FamilyEvent, Membership, Note, NoteShare, Routine, ShoppingItem, ShoppingList, Task, Trip
from .pin_adapters import get_pin_adapter


class PinPickerContextTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('context-picker-owner')
        self.child = User.objects.create_user('context-picker-child')
        self.foreign_user = User.objects.create_user('context-picker-foreign')
        self.family = Family.objects.create(name='Context picker', slug='context-picker')
        self.foreign = Family.objects.create(name='Other', slug='context-picker-other')
        self.owner_member = Membership.objects.create(family=self.family, user=self.owner, role='owner')
        self.child_member = Membership.objects.create(family=self.family, user=self.child, role='child')
        Membership.objects.create(family=self.foreign, user=self.foreign_user, role='owner')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def lookup(self, key, target_id, **params):
        return self.client.get('/api/board/picker/', {
            'family': str(self.family.id), 'adapter_key': key,
            'target_id': str(target_id), **params,
        })

    def document(self):
        return Document.objects.create(
            family=self.family, title='Private source',
            visibility=Document.Visibility.SELECTED, owner_membership=self.owner_member,
            canonical_file='documents/context-test.pdf', mime_type='application/pdf',
            size=1, sha256='b' * 64, created_by=self.owner,
        )

    def test_exact_lookup_all_adapters_matches_canonical_preview_without_mutation(self):
        shopping = ShoppingList.objects.create(family=self.family, name='List')
        cases = {
            'task': Task.objects.create(family=self.family, title='Task', created_by=self.owner),
            'routine': Routine.objects.create(family=self.family, name='Routine'),
            'calendar_event': FamilyEvent.objects.create(family=self.family, type='family', title='Event'),
            'note': Note.objects.create(family=self.family, author=self.owner, title='Note', body='Body'),
            'shopping_list': shopping,
            'shopping_item': ShoppingItem.objects.create(shopping_list=shopping, name='Item'),
            'trip': Trip.objects.create(family=self.family, title='Trip', destination='Berlin', starts_on=date(2027, 1, 1), ends_on=date(2027, 1, 2), created_by=self.owner),
            'document': self.document(),
        }
        for key, row in cases.items():
            with self.subTest(key=key):
                adapter = get_pin_adapter(key)
                self.assertTrue(adapter.can_pin(self.owner, self.family.id, row.id))
                listing = self.client.get('/api/board/picker/', {'family': str(self.family.id), 'adapter_key': key})
                expected = next(item for item in listing.data['results'] if item['id'] == str(row.id))
                response = self.lookup(key, row.id)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['adapter_key'], key)
                self.assertEqual(response.data['results'], [expected])
                self.assertFalse(response.data['has_next'])
        self.assertFalse(BoardPost.objects.exists())
        self.assertFalse(NoteShare.objects.exists())
        self.assertFalse(DocumentAccess.objects.exists())

    def test_exact_filter_precedes_pagination_and_search_never_falls_back(self):
        target = Task.objects.create(family=self.family, title='Older task', created_by=self.owner)
        Task.objects.bulk_create([Task(family=self.family, title=f'New task {index}', created_by=self.owner) for index in range(55)])
        response = self.lookup('task', target.id, page_size=1)
        self.assertEqual([row['id'] for row in response.data['results']], [str(target.id)])
        self.assertFalse(response.data['has_next'])
        for params in ({'page': 2, 'page_size': 1}, {'q': 'New task'}):
            with self.subTest(params=params):
                response = self.lookup('task', target.id, **params)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['results'], [])
                self.assertFalse(response.data['has_next'])

    def test_denied_foreign_missing_and_deleted_ids_have_identical_empty_responses(self):
        hidden = Task.objects.create(family=self.family, title='Secret gift', created_by=self.owner, hidden_from_user=self.child)
        foreign = Task.objects.create(family=self.foreign, title='Other family secret', created_by=self.foreign_user)
        deleted = Task.objects.create(family=self.family, title='Deleted secret', created_by=self.owner)
        deleted_id = deleted.id
        deleted.delete()
        self.client.force_authenticate(self.child)
        baseline = self.lookup('task', uuid.uuid4())
        self.assertEqual(baseline.status_code, 200, baseline.data)
        self.assertEqual(baseline.data['results'], [])
        for target_id in (hidden.id, foreign.id, deleted_id):
            with self.subTest(target_id=target_id):
                response = self.lookup('task', target_id)
                self.assertEqual(response.status_code, baseline.status_code)
                self.assertEqual(response.data, baseline.data)

    def test_note_and_document_permissions_are_rechecked_after_revocation(self):
        note = Note.objects.create(family=self.family, author=self.owner, title='Secret note', body='Never expose after revoke')
        document = self.document()
        self.client.force_authenticate(self.child)
        for key, row, share in (
            ('note', note, lambda: NoteShare.objects.create(note=note, user=self.child, permission='read')),
            ('document', document, lambda: DocumentAccess.objects.create(document=document, membership=self.child_member, can_view=True)),
        ):
            with self.subTest(key=key):
                denied = self.lookup(key, row.id)
                self.assertEqual(denied.status_code, 200, denied.data)
                self.assertEqual(denied.data['results'], [])
                access = share()
                allowed = self.lookup(key, row.id)
                self.assertEqual(allowed.data['results'][0]['id'], str(row.id))
                access.delete()
                revoked = self.lookup(key, row.id)
                self.assertEqual(revoked.data, denied.data)
                self.assertEqual(revoked.data, self.lookup(key, uuid.uuid4()).data)
                save = self.client.post('/api/board/', {
                    'family': str(self.family.id), 'adapter_key': key,
                    'target_id': allowed.data['results'][0]['id'],
                }, format='json')
                self.assertEqual(save.status_code, 400, save.data)
                self.assertIn('target_id', save.data)
                self.assertFalse(BoardPost.objects.exists())

    def test_exact_shopping_lookup_does_not_expose_hidden_gifts_or_foreign_lists(self):
        shopping = ShoppingList.objects.create(family=self.family, name='List')
        foreign_list = ShoppingList.objects.create(family=self.foreign, name='Other list')
        gift = ShoppingItem.objects.create(shopping_list=shopping, name='Secret gift', hidden_from_user=self.child)
        foreign_item = ShoppingItem.objects.create(shopping_list=foreign_list, name='Foreign secret')
        self.client.force_authenticate(self.child)
        for key, target in (('shopping_item', gift), ('shopping_item', foreign_item), ('shopping_list', foreign_list)):
            with self.subTest(key=key, target=target.id):
                response = self.lookup(key, target.id)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data['results'], [])
                self.assertEqual(response.data, self.lookup(key, uuid.uuid4()).data)

    def test_archived_routine_list_and_document_cannot_be_preselected(self):
        routine = Routine.objects.create(family=self.family, name='Archived', active=False)
        shopping = ShoppingList.objects.create(family=self.family, name='Archived', archived=True)
        document = self.document()
        document.archived_at = timezone.now()
        document.save(update_fields=['archived_at'])
        for key, row in (('routine', routine), ('shopping_list', shopping), ('document', document)):
            with self.subTest(key=key):
                adapter = get_pin_adapter(key)
                self.assertTrue(adapter.can_view(self.owner, self.family.id, row.id))
                self.assertFalse(adapter.can_pin(self.owner, self.family.id, row.id))
                response = self.lookup(key, row.id)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data, self.lookup(key, uuid.uuid4()).data)

    def test_invalid_target_does_not_read_or_preview_sources(self):
        adapter = get_pin_adapter('task')
        for target_id in ('', 'not-a-uuid', '1', 'null'):
            with self.subTest(target_id=target_id), patch.object(adapter, 'pinnable_queryset') as selector, patch.object(adapter, 'preview') as preview:
                response = self.lookup('task', target_id)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn('target_id', response.data)
                selector.assert_not_called()
                preview.assert_not_called()

    def test_exact_lookup_is_bounded_to_one_preview_and_two_queries(self):
        task = Task.objects.create(family=self.family, title='Task', created_by=self.owner)
        adapter = get_pin_adapter('task')
        with patch.object(adapter, 'preview', wraps=adapter.preview) as preview, CaptureQueriesContext(connection) as captured:
            response = self.lookup('task', task.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(preview.call_count, 1)
        self.assertEqual(len(captured), 2, [query['sql'] for query in captured])

    def test_exact_lookup_keeps_legacy_alias_and_family_role_gates(self):
        event = FamilyEvent.objects.create(family=self.family, type='family', title='Event')
        canonical = self.lookup('calendar_event', event.id)
        legacy = self.client.get('/api/board/picker/', {'family': str(self.family.id), 'kind': 'event', 'target_id': str(event.id)})
        self.assertEqual(canonical.status_code, 200, canonical.data)
        self.assertEqual(legacy.data, canonical.data)
        self.assertEqual(self.lookup('unknown', event.id).status_code, 400)
        self.assertEqual(self.lookup('calendar_event', event.id, family=str(self.foreign.id)).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.lookup('calendar_event', event.id).status_code, (401, 403))
        self.client.force_authenticate(self.foreign_user)
        self.assertEqual(self.lookup('calendar_event', event.id).status_code, 403)
        self.client.force_authenticate(self.child)
        self.child_member.role = Membership.Role.GUEST
        self.child_member.save(update_fields=['role'])
        self.assertEqual(self.lookup('calendar_event', event.id).status_code, 403)
        self.client.force_authenticate(self.owner)
        self.family.status = Family.Status.SUSPENDED
        self.family.save(update_fields=['status'])
        self.assertEqual(self.lookup('calendar_event', event.id).status_code, 403)
