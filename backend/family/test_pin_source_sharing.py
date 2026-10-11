from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BoardPost, Family, Membership, Note, NoteShare


class PinSourceSharingCapabilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('pin-share-owner')
        self.reader = User.objects.create_user('pin-share-reader')
        self.family = Family.objects.create(name='Pin source sharing', slug='pin-source-sharing')
        Membership.objects.create(family=self.family, user=self.owner, role='owner')
        Membership.objects.create(family=self.family, user=self.reader, role='adult')
        self.note = Note.objects.create(
            family=self.family,
            author=self.owner,
            title='Canonical source sharing',
            body='The board must delegate this ACL.',
        )
        NoteShare.objects.create(note=self.note, user=self.reader, permission='read')
        self.pin = BoardPost.objects.create(
            family=self.family,
            author=self.owner,
            kind=BoardPost.Kind.NOTE_REF,
            adapter_key='note',
            target_id=self.note.id,
            visibility=BoardPost.Visibility.FAMILY,
        )
        self.client = APIClient()

    def _pin_for(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['results']), 1)
        return response.data['results'][0]

    def test_note_owner_gets_explicit_canonical_source_share_deep_link(self):
        row = self._pin_for(self.owner)
        self.assertTrue(row['can_share_source'])
        self.assertTrue(row['target']['can_share_source'])
        self.assertEqual(
            row['target']['source_share_url'],
            f'/?page=notes&note={self.note.id}&share=1',
        )

    def test_non_owner_never_gets_source_share_capability(self):
        row = self._pin_for(self.reader)
        self.assertFalse(row['can_share_source'])
        self.assertNotIn('can_share_source', row['target'])
        self.assertNotIn('source_share_url', row['target'])
