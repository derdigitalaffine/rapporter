import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from documents.models import Document, DocumentAccess

from .models import (
    BoardImage,
    BoardPost,
    Family,
    Membership,
    Note,
    NoteShare,
    ShoppingItem,
    ShoppingList,
    Task,
)
from .pin_visibility import can_view_pin, effective_scope_for_user, visible_pin_memberships


class PinVisibilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('visibility-owner')
        self.selected = User.objects.create_user('visibility-selected')
        self.other = User.objects.create_user('visibility-other')
        self.guest = User.objects.create_user('visibility-guest')
        self.foreign_user = User.objects.create_user('visibility-foreign')
        self.family = Family.objects.create(name='Visibility', slug='visibility')
        self.foreign = Family.objects.create(name='Foreign visibility', slug='foreign-visibility')
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role='owner')
        self.selected_membership = Membership.objects.create(family=self.family, user=self.selected, role='child')
        self.other_membership = Membership.objects.create(family=self.family, user=self.other, role='adult')
        self.guest_membership = Membership.objects.create(family=self.family, user=self.guest, role='guest')
        self.foreign_membership = Membership.objects.create(family=self.foreign, user=self.foreign_user, role='owner')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _rows(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results']

    def test_private_native_pin_is_author_only_and_reports_server_scope(self):
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'note',
            'text': 'Nur für mich',
            'visibility': 'private',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['visibility'], 'private')
        self.assertEqual(response.data['effective_scope'], 'private')
        self.assertTrue(response.data['can_change_pin_visibility'])
        self.assertTrue(response.data['can_interact'])
        self.assertFalse(response.data['can_share_source'])

        pin_id = response.data['id']
        self.assertEqual([row['id'] for row in self._rows(self.owner)], [pin_id])
        self.assertEqual(self._rows(self.selected), [])
        hidden = self.client.get(f'/api/board/{pin_id}/?family={self.family.id}')
        self.assertEqual(hidden.status_code, 404)

    def test_selected_visibility_uses_membership_grants_and_membership_lifecycle(self):
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'note',
            'text': 'Ausgewählt',
            'visibility': 'selected',
            'selected_membership_ids': [str(self.selected_membership.id)],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['selected_membership_ids'], [str(self.selected_membership.id)])
        pin_id = response.data['id']

        selected_rows = self._rows(self.selected)
        self.assertEqual([row['id'] for row in selected_rows], [pin_id])
        self.assertEqual(selected_rows[0]['selected_membership_ids'], [])
        self.assertEqual(self._rows(self.other), [])

        self.selected_membership.delete()
        pin = BoardPost.objects.get(pk=pin_id)
        self.assertEqual(pin.visible_to_memberships.count(), 0)
        self.client.force_authenticate(self.selected)
        response = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(response.status_code, 403)

    def test_family_visibility_includes_guest_readers(self):
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'note',
            'text': 'Für alle',
            'visibility': 'family',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        rows = self._rows(self.guest)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['text'], 'Für alle')
        self.assertFalse(rows[0]['can_change_pin_visibility'])

    def test_cross_family_and_guessed_selected_membership_ids_fail_identically(self):
        payload = {
            'family': str(self.family.id),
            'kind': 'note',
            'text': 'Nicht leaken',
            'visibility': 'selected',
        }
        foreign = self.client.post('/api/board/', {
            **payload,
            'selected_membership_ids': [str(self.foreign_membership.id)],
        }, format='json')
        missing = self.client.post('/api/board/', {
            **payload,
            'selected_membership_ids': [str(uuid.uuid4())],
        }, format='json')
        self.assertEqual(foreign.status_code, 400)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(foreign.data, missing.data)
        self.assertFalse(BoardPost.objects.filter(text='Nicht leaken').exists())

    def test_reference_effective_access_is_pin_scope_intersected_with_source_acl(self):
        note = Note.objects.create(family=self.family, author=self.owner, title='Privatquelle', body='Geheim')
        created = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'note_ref',
            'target_id': str(note.id),
            'text': 'Sensitive pin caption',
            'visibility': 'family',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        pin = BoardPost.objects.get(pk=created.data['id'])

        hidden = self._rows(self.selected)[0]
        self.assertEqual(hidden['target'], {'id': str(note.id), 'kind': 'note_ref', 'available': False})
        self.assertEqual(hidden['effective_scope'], 'none')
        self.assertFalse(hidden['can_interact'])
        self.assertEqual(hidden['text'], '')
        self.assertEqual(hidden['images'], [])
        self.assertIsNone(hidden['author'])
        self.assertEqual(hidden['author_name'], '')
        self.assertIsNone(hidden['created_at'])
        self.assertIsNone(hidden['updated_at'])
        self.assertFalse(hidden['can_edit'])
        self.assertFalse(hidden['can_reorder'])
        self.assertFalse(hidden['can_change_pin_visibility'])
        self.assertFalse(hidden['can_delete'])
        self.assertNotIn('Sensitive pin caption', str(hidden))
        self.assertFalse(can_view_pin(self.selected, pin))
        self.assertEqual(effective_scope_for_user(self.selected, pin), 'none')

        share = NoteShare.objects.create(note=note, user=self.selected, permission='read')
        visible = self._rows(self.selected)[0]
        self.assertEqual(visible['target']['title'], 'Privatquelle')
        self.assertEqual(visible['text'], 'Sensitive pin caption')
        self.assertEqual(visible['effective_scope'], 'selected')
        self.assertTrue(visible['can_interact'])
        self.assertTrue(can_view_pin(self.selected, pin))
        self.assertEqual(effective_scope_for_user(self.selected, pin), 'selected')

        share.delete()
        revoked = self._rows(self.selected)[0]
        self.assertEqual(revoked['effective_scope'], 'none')
        self.assertFalse(revoked['can_interact'])
        self.assertEqual(revoked['text'], '')
        self.assertNotIn('Sensitive pin caption', str(revoked))
        self.assertNotIn('Privatquelle', str(revoked))
        self.assertNotIn('Geheim', str(revoked))

    def test_document_acl_is_canonical_for_reference_pin(self):
        document = Document.objects.create(
            family=self.family,
            title='Selected document',
            visibility=Document.Visibility.SELECTED,
            owner_membership=self.owner_membership,
            canonical_file='documents/test.pdf',
            mime_type='application/pdf',
            size=1,
            sha256='a' * 64,
            created_by=self.owner,
        )
        access = DocumentAccess.objects.create(
            document=document,
            membership=self.selected_membership,
            can_view=True,
        )
        created = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'document',
            'target_id': str(document.id),
            'text': 'document caption must follow ACL',
            'visibility': 'family',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)

        selected = self._rows(self.selected)[0]
        self.assertEqual(selected['target']['title'], 'Selected document')
        self.assertEqual(selected['effective_scope'], 'selected')
        other = self._rows(self.other)[0]
        self.assertEqual(other['effective_scope'], 'none')
        self.assertEqual(other['text'], '')
        self.assertNotIn('Selected document', str(other))
        self.assertNotIn('document caption', str(other))

        access.delete()
        revoked = self._rows(self.selected)[0]
        self.assertEqual(revoked['effective_scope'], 'none')
        self.assertEqual(revoked['text'], '')
        self.assertNotIn('Selected document', str(revoked))

    def test_hidden_birthday_gift_task_and_item_stay_neutral(self):
        task = Task.objects.create(
            family=self.family,
            title='Geheime Geburtstagsaufgabe',
            created_by=self.owner,
            hidden_from_user=self.selected,
        )
        shopping_list = ShoppingList.objects.create(family=self.family, name='Geschenke')
        item = ShoppingItem.objects.create(
            shopping_list=shopping_list,
            name='Geheimes Geschenk',
            hidden_from_user=self.selected,
        )
        task_pin = BoardPost.objects.create(
            family=self.family,
            author=self.owner,
            kind=BoardPost.Kind.TASK,
            target_id=task.id,
            text='task surprise caption',
            visibility=BoardPost.Visibility.FAMILY,
        )
        item_pin = BoardPost.objects.create(
            family=self.family,
            author=self.owner,
            kind=BoardPost.Kind.SHOPPING,
            target_id=item.id,
            text='item surprise caption',
            visibility=BoardPost.Visibility.FAMILY,
        )

        rows = {row['id']: row for row in self._rows(self.selected)}
        for pin, secret in ((task_pin, 'Geheime Geburtstagsaufgabe'), (item_pin, 'Geheimes Geschenk')):
            row = rows[str(pin.id)]
            self.assertEqual(row['effective_scope'], 'none')
            self.assertFalse(row['can_interact'])
            self.assertEqual(row['text'], '')
            self.assertFalse(row['target'].get('available', True))
            self.assertNotIn(secret, str(row))
        self.assertNotIn('task surprise caption', str(rows))
        self.assertNotIn('item surprise caption', str(rows))

    def test_unregistered_sensitive_domain_adapters_fail_closed(self):
        # School, Pet/Care and direct CalDAV objects do not have a Pin adapter yet.
        # They must remain unpinnable instead of falling back to a generic lookup
        # that could bypass their canonical domain permissions/free-busy rules.
        for adapter_key in ('school', 'pet', 'care', 'caldav_event'):
            response = self.client.post('/api/board/', {
                'family': str(self.family.id),
                'kind': 'note',
                'adapter_key': adapter_key,
                'target_id': str(uuid.uuid4()),
                'visibility': 'family',
            }, format='json')
            self.assertEqual(response.status_code, 400, (adapter_key, response.data))
            self.assertIn('adapter_key', response.data)
        self.assertEqual(BoardPost.objects.count(), 0)

    def test_pin_scope_can_be_narrower_than_family_visible_source(self):
        task = Task.objects.create(family=self.family, title='Familienaufgabe', created_by=self.owner)
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'task',
            'target_id': str(task.id),
            'visibility': 'private',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        pin = BoardPost.objects.get(pk=response.data['id'])
        self.assertEqual(response.data['effective_scope'], 'private')
        self.assertFalse(can_view_pin(self.selected, pin))
        self.assertEqual(self._rows(self.selected), [])

    def test_family_reference_reports_family_only_when_every_membership_can_see_source(self):
        task = Task.objects.create(family=self.family, title='Für die Familie', created_by=self.owner)
        response = self.client.post('/api/board/', {
            'family': str(self.family.id),
            'kind': 'task',
            'target_id': str(task.id),
            'visibility': 'family',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['effective_scope'], 'family')
        row = self._rows(self.guest)[0]
        self.assertEqual(row['effective_scope'], 'family')
        self.assertTrue(row['can_interact'])

    def test_visible_membership_resolver_applies_source_acl_without_widening(self):
        note = Note.objects.create(family=self.family, author=self.owner, title='Resolver', body='Secret')
        pin = BoardPost.objects.create(
            family=self.family,
            author=self.owner,
            kind=BoardPost.Kind.NOTE_REF,
            target_id=note.id,
            visibility=BoardPost.Visibility.FAMILY,
        )
        self.assertEqual(set(visible_pin_memberships(pin).values_list('id', flat=True)), {self.owner_membership.id})
        NoteShare.objects.create(note=note, user=self.selected, permission='read')
        self.assertEqual(
            set(visible_pin_memberships(pin).values_list('id', flat=True)),
            {self.owner_membership.id, self.selected_membership.id},
        )

    def test_hidden_pin_ids_do_not_become_reorder_or_image_oracles(self):
        private_pin = BoardPost.objects.create(
            family=self.family,
            author=self.owner,
            kind=BoardPost.Kind.PHOTO,
            text='private photo',
            visibility=BoardPost.Visibility.PRIVATE,
        )
        image = BoardImage.objects.create(post=private_pin, key='0' * 32, width=10, height=10)
        BoardPost.objects.create(family=self.family, author=self.owner, text='public', visibility=BoardPost.Visibility.FAMILY)

        self.client.force_authenticate(self.selected)
        hidden = self.client.post('/api/board/reorder/', {
            'family': str(self.family.id),
            'ids': [str(private_pin.id)],
        }, format='json')
        missing = self.client.post('/api/board/reorder/', {
            'family': str(self.family.id),
            'ids': [str(uuid.uuid4())],
        }, format='json')
        self.assertEqual(hidden.status_code, 400)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(hidden.data, missing.data)
        self.assertEqual(self.client.get(f'/api/board-images/{image.id}/').status_code, 404)
