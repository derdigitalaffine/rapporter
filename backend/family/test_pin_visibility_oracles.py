import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import BoardPost, Family, Membership, Note


class PinVisibilityOracleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('pin-oracle-user')
        self.other = User.objects.create_user('pin-oracle-other')
        self.family = Family.objects.create(name='Oracle A', slug='oracle-a')
        self.foreign = Family.objects.create(name='Oracle B', slug='oracle-b')
        Membership.objects.create(family=self.family, user=self.user, role='owner')
        Membership.objects.create(family=self.family, user=self.other, role='child')
        # The actor may legitimately see both families. A visible object in B still
        # must not become a valid target for a Pin in A.
        Membership.objects.create(family=self.foreign, user=self.user, role='owner')
        self.foreign_note = Note.objects.create(
            family=self.foreign,
            author=self.user,
            title='Foreign but visible',
            body='Must not cross family boundaries.',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_cross_family_and_guessed_target_ids_fail_identically(self):
        payload = {
            'family': str(self.family.id),
            'kind': 'note_ref',
            'visibility': 'family',
        }
        foreign = self.client.post('/api/board/', {
            **payload,
            'target_id': str(self.foreign_note.id),
        }, format='json')
        missing = self.client.post('/api/board/', {
            **payload,
            'target_id': str(uuid.uuid4()),
        }, format='json')
        self.assertEqual(foreign.status_code, 400)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(foreign.data, missing.data)
        self.assertEqual(BoardPost.objects.count(), 0)

    def test_hidden_and_guessed_pin_ids_are_both_404(self):
        private_pin = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            text='private',
            visibility=BoardPost.Visibility.PRIVATE,
        )
        self.client.force_authenticate(self.other)
        hidden = self.client.get(f'/api/board/{private_pin.id}/')
        missing = self.client.get(f'/api/board/{uuid.uuid4()}/')
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(missing.status_code, 404)

    def test_source_denied_reorder_matches_random_id_and_preserves_positions(self):
        source = Note.objects.create(family=self.family, author=self.other, title='Private source')
        pin = BoardPost.objects.create(
            family=self.family, author=self.other, kind='note_ref',
            target_id=source.pk, visibility=BoardPost.Visibility.FAMILY, position=1000,
        )
        before = list(BoardPost.objects.filter(family=self.family).values_list('id', 'position'))
        denied = self.client.post('/api/board/reorder/', {
            'family': str(self.family.pk), 'ids': [str(pin.pk)],
        }, format='json')
        guessed = self.client.post('/api/board/reorder/', {
            'family': str(self.family.pk), 'ids': [str(uuid.uuid4())],
        }, format='json')
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(denied.data, guessed.data)
        self.assertEqual(list(BoardPost.objects.filter(family=self.family).values_list('id', 'position')), before)
