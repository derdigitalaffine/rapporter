import uuid
from dataclasses import replace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from telemetry.models import AuditEvent

from .models import BoardPost, Family, Membership, Note, NoteShare, PinComment, PinReaction


class PinInteractionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('pin-owner')
        self.adult = User.objects.create_user('pin-adult')
        self.child = User.objects.create_user('pin-child')
        self.outsider = User.objects.create_user('pin-outsider')
        self.family = Family.objects.create(name='Pins', slug='pin-interactions')
        self.other = Family.objects.create(name='Elsewhere', slug='pin-interactions-other')
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role='owner', display_name='Owner')
        self.adult_membership = Membership.objects.create(family=self.family, user=self.adult, role='adult', display_name='Adult')
        self.child_membership = Membership.objects.create(family=self.family, user=self.child, role='child', display_name='Child')
        Membership.objects.create(family=self.other, user=self.outsider, role='owner')
        self.pin = BoardPost.objects.create(family=self.family, author=self.owner, text='Familienpin', visibility='family')
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def board_row(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(f'/api/board/?family={self.family.id}')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['results'][0]

    def test_card_reaction_put_is_idempotent_replace_and_explicit_remove(self):
        self.client.force_authenticate(self.adult)
        url = f'/api/board/{self.pin.id}/reaction/'
        first = self.client.put(url, {'key': 'thumbs_up'}, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['reactions'], [{'key': 'thumbs_up', 'count': 1, 'mine': True}])

        retry = self.client.put(url, {'key': 'thumbs_up'}, format='json')
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(PinReaction.objects.filter(pin=self.pin, comment__isnull=True).count(), 1)

        replaced = self.client.put(url, {'key': 'heart'}, format='json')
        self.assertEqual(replaced.data['reactions'], [{'key': 'heart', 'count': 1, 'mine': True}])
        self.assertEqual(PinReaction.objects.get(pin=self.pin, membership=self.adult_membership).key, 'heart')

        removed = self.client.put(url, {'key': None}, format='json')
        self.assertEqual(removed.data['reactions'], [])
        self.assertFalse(PinReaction.objects.filter(pin=self.pin, membership=self.adult_membership).exists())

    def test_comment_create_retry_is_deduplicated_and_summary_updates(self):
        self.client.force_authenticate(self.adult)
        client_id = str(uuid.uuid4())
        url = f'/api/board/{self.pin.id}/comments/'
        payload = {'body': 'Bin dabei.', 'client_id': client_id}
        created = self.client.post(url, payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        retry = self.client.post(url, payload, format='json')
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(created.data['id'], retry.data['id'])
        self.assertEqual(PinComment.objects.filter(pin=self.pin).count(), 1)

        row = self.board_row(self.owner)
        self.assertEqual(row['interaction']['comment_count'], 1)
        self.assertTrue(row['interaction']['has_unread_comments'])
        self.assertNotIn('Bin dabei.', str(row['interaction']))

        comments = self.client.get(url)
        self.assertEqual(comments.status_code, 200, comments.data)
        row = self.board_row(self.owner)
        self.assertFalse(row['interaction']['has_unread_comments'])

    def test_mentions_are_limited_to_effective_pin_viewers(self):
        selected = BoardPost.objects.create(
            family=self.family,
            author=self.owner,
            text='Ausgewählt',
            visibility='selected',
        )
        selected.visible_to_memberships.add(self.adult_membership)
        url = f'/api/board/{selected.id}/comments/'
        bad = self.client.post(url, {
            'body': '@Child bitte prüfen',
            'client_id': str(uuid.uuid4()),
            'mention_membership_ids': [str(self.child_membership.id)],
        }, format='json')
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(PinComment.objects.filter(pin=selected).count(), 0)

        good = self.client.post(url, {
            'body': '@Adult bitte prüfen',
            'client_id': str(uuid.uuid4()),
            'mention_membership_ids': [str(self.adult_membership.id)],
        }, format='json')
        self.assertEqual(good.status_code, 201, good.data)
        self.assertEqual(good.data['mentions'], [{'id': str(self.adult_membership.id), 'name': 'Adult'}])
        targets = self.client.get(f'/api/board/{selected.id}/mention-targets/')
        self.assertEqual({row['id'] for row in targets.data}, {str(self.owner_membership.id), str(self.adult_membership.id)})

    def test_source_revoke_hides_thread_and_all_interaction_counts(self):
        note = Note.objects.create(family=self.family, author=self.owner, title='Privatquelle', body='Geheim')
        share = NoteShare.objects.create(note=note, user=self.adult, permission='read')
        pin = BoardPost.objects.create(
            family=self.family,
            author=self.owner,
            text='Sensitive caption',
            kind='note_ref',
            target_id=note.id,
            adapter_key='note',
            visibility='family',
        )
        self.client.force_authenticate(self.adult)
        created = self.client.post(f'/api/board/{pin.id}/comments/', {
            'body': 'Sensitive discussion',
            'client_id': str(uuid.uuid4()),
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.client.put(f'/api/board/{pin.id}/reaction/', {'key': 'seen'}, format='json')

        share.delete()
        denied = self.client.get(f'/api/board/{pin.id}/comments/')
        self.assertEqual(denied.status_code, 404)
        row = self.board_row(self.adult)
        self.assertEqual(row['effective_scope'], 'none')
        self.assertFalse(row['can_interact'])
        self.assertEqual(row['interaction'], {
            'comment_count': 0,
            'has_unread_comments': False,
            'reactions': [],
            'can_interact': False,
            'muted': False,
        })
        self.assertNotIn('Sensitive discussion', str(row))

    def test_comment_edit_comment_reaction_and_owner_tombstone_moderation(self):
        self.client.force_authenticate(self.adult)
        created = self.client.post(f'/api/board/{self.pin.id}/comments/', {
            'body': 'Erster Text',
            'client_id': str(uuid.uuid4()),
        }, format='json')
        comment_id = created.data['id']
        detail = f'/api/board/{self.pin.id}/comments/{comment_id}/'
        edited = self.client.patch(detail, {'body': 'Korrigierter Text'}, format='json')
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(edited.data['body'], 'Korrigierter Text')

        reacted = self.client.put(f'/api/board/{self.pin.id}/comments/{comment_id}/reaction/', {'key': 'celebrate'}, format='json')
        self.assertEqual(reacted.status_code, 200, reacted.data)
        self.assertEqual(reacted.data['reactions'], [{'key': 'celebrate', 'count': 1, 'mine': True}])

        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.patch(detail, {'body': 'Nein'}, format='json').status_code, 404)

        self.client.force_authenticate(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            deleted = self.client.delete(detail)
        self.assertEqual(deleted.status_code, 200, deleted.data)
        comment = PinComment.objects.get(pk=comment_id)
        self.assertEqual(comment.body, '')
        self.assertIsNotNone(comment.deleted_at)
        self.assertFalse(PinReaction.objects.filter(comment=comment).exists())
        self.assertTrue(AuditEvent.objects.filter(
            event_key='pin.comment.moderated',
            target_type='pin_comment',
            target_id=str(comment.id),
        ).exists())

    def test_cross_family_interaction_ids_are_neutral(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f'/api/board/{self.pin.id}/comments/').status_code, 404)
        self.assertEqual(self.client.put(f'/api/board/{self.pin.id}/reaction/', {'key': 'heart'}, format='json').status_code, 404)
        self.assertEqual(self.client.get(f'/api/board/{self.pin.id}/mention-targets/').status_code, 404)

    def test_reaction_put_does_not_enable_board_replacement(self):
        response = self.client.put(f'/api/board/{self.pin.id}/', {'text': 'Replacement'}, format='json')
        self.assertEqual(response.status_code, 405)
        self.pin.refresh_from_db()
        self.assertEqual(self.pin.text, 'Familienpin')

    def test_malformed_comment_inputs_are_bounded_validation_errors(self):
        url = f'/api/board/{self.pin.id}/comments/'
        for changes in ({'body': {'private': 'object'}}, {'mention_membership_ids': ['not-a-uuid']}, {'mention_membership_ids': {}}, {'mention_membership_ids': [str(self.adult_membership.id)] * 101}):
            payload = {'body': 'Comment', 'client_id': str(uuid.uuid4()), **changes}
            response = self.client.post(url, payload, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(PinComment.objects.exists())

    def test_central_burst_limit_blocks_mutations_without_blocking_reads(self):
        from auth_abuse.service import get_policy, WindowPolicy, KeyPolicy
        policy = replace(get_policy('pin.interaction'), burst=WindowPolicy(1, 60), keys=(KeyPolicy('user'),))
        url = f'/api/board/{self.pin.id}/reaction/'
        with patch('auth_abuse.service.get_policy', return_value=policy):
            self.assertEqual(self.client.put(url, {'key': 'heart'}, format='json').status_code, 200)
            blocked = self.client.put(url, {'key': 'seen'}, format='json')
            self.assertEqual(blocked.status_code, 429)
            self.assertGreater(int(blocked['Retry-After']), 0)
            self.assertEqual(self.client.get(f'/api/board/{self.pin.id}/comments/').status_code, 200)
        self.assertEqual(PinReaction.objects.get(pin=self.pin).key, 'heart')

    def test_deleted_comment_cannot_be_edited_or_reacted_to(self):
        created = self.client.post(f'/api/board/{self.pin.id}/comments/', {'body': 'Removed body', 'client_id': str(uuid.uuid4())}, format='json')
        detail = f'/api/board/{self.pin.id}/comments/{created.data["id"]}/'
        self.assertEqual(self.client.delete(detail).status_code, 200)
        self.assertEqual(self.client.patch(detail, {'body': 'Resurrected'}, format='json').status_code, 404)
        self.assertEqual(self.client.put(detail + 'reaction/', {'key': 'heart'}, format='json').status_code, 404)
        comment = PinComment.objects.get(pk=created.data['id'])
        self.assertEqual(comment.body, '')
        self.assertFalse(comment.reactions.exists())

    def test_summary_query_budget_is_independent_of_pin_count(self):
        from .pin_interactions import build_pin_interaction_summaries
        pins = [self.pin] + [BoardPost.objects.create(family=self.family, author=self.owner, text='Pin') for _ in range(19)]
        for page in ([self.pin], pins):
            with self.assertNumQueries(6):
                summaries = build_pin_interaction_summaries(page, self.owner, visible_pin_ids={pin.id for pin in page})
            self.assertEqual(len(summaries), len(page))

    def test_malformed_subject_ids_are_neutral_and_missing_state_is_not_remove(self):
        self.assertEqual(self.client.get('/api/board/not-a-uuid/comments/').status_code, 404)
        self.assertEqual(self.client.patch(f'/api/board/{self.pin.id}/comments/aaaa/', {'body': 'No'}, format='json').status_code, 404)
        url = f'/api/board/{self.pin.id}/reaction/'
        self.assertEqual(self.client.put(url, {'key': 'heart'}, format='json').status_code, 200)
        self.assertEqual(self.client.put(url, {}, format='json').status_code, 400)
        self.assertEqual(self.client.put(url, [], format='json').status_code, 400)
        self.assertEqual(PinReaction.objects.get(pin=self.pin).key, 'heart')

    def test_old_comment_retry_does_not_regress_personal_seen_timestamp(self):
        from .board_models import PinInteractionState
        from django.utils import timezone
        from datetime import timedelta
        client_id = str(uuid.uuid4())
        url = f'/api/board/{self.pin.id}/comments/'
        payload = {'body': 'First', 'client_id': client_id}
        self.assertEqual(self.client.post(url, payload, format='json').status_code, 201)
        seen = timezone.now() + timedelta(seconds=1)
        PinInteractionState.objects.filter(pin=self.pin, membership=self.owner_membership).update(last_seen_comment_at=seen)
        self.assertEqual(self.client.post(url, payload, format='json').status_code, 200)
        self.assertEqual(PinInteractionState.objects.get(pin=self.pin, membership=self.owner_membership).last_seen_comment_at, seen)

    def test_shared_summary_helper_defaults_to_canonical_visibility(self):
        from .pin_interactions import build_pin_interaction_summaries
        self.pin.visibility = 'private'
        self.pin.save(update_fields=['visibility'])
        self.assertEqual(build_pin_interaction_summaries([self.pin], self.adult), {})
        self.assertIn(self.pin.id, build_pin_interaction_summaries([self.pin], self.owner))

    def test_comment_arriving_after_page_snapshot_remains_unread(self):
        from .pin_interactions import PinCommentPagination
        first = PinComment.objects.create(pin=self.pin, family=self.family, author=self.adult, body='Delivered', client_id=uuid.uuid4())
        original = PinCommentPagination.paginate_queryset
        def snapshot_then_arrival(paginator, *args, **kwargs):
            page = original(paginator, *args, **kwargs)
            PinComment.objects.create(pin=self.pin, family=self.family, author=self.adult, body='Later arrival', client_id=uuid.uuid4())
            return page
        with patch.object(PinCommentPagination, 'paginate_queryset', snapshot_then_arrival):
            response = self.client.get(f'/api/board/{self.pin.id}/comments/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data['results']], [str(first.id)])
        self.assertTrue(self.board_row(self.owner)['interaction']['has_unread_comments'])
