import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from notifications.models import Notification
from django.utils import timezone

from .models import BoardPost, Family, Membership, Note, NoteShare


class PinInteractionNotificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("interaction-notify-owner")
        self.member = User.objects.create_user("interaction-notify-member")
        self.family = Family.objects.create(name="Notify family", slug="interaction-notify")
        self.owner_membership = Membership.objects.create(
            family=self.family, user=self.owner, role="owner", display_name="Owner"
        )
        self.member_membership = Membership.objects.create(
            family=self.family, user=self.member, role="adult", display_name="Member"
        )
        self.note = Note.objects.create(
            family=self.family,
            author=self.owner,
            title="Private source",
            body="Sensitive source body",
        )
        self.share = NoteShare.objects.create(note=self.note, user=self.member, permission="read")
        self.pin = BoardPost.objects.create(
            family=self.family,
            author=self.owner,
            text="Sensitive pin caption",
            kind="note_ref",
            target_id=self.note.id,
            adapter_key="note",
            visibility="family",
        )
        self.client = APIClient()

    def _comment(self, user, body):
        self.client.force_authenticate(user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/board/{self.pin.id}/comments/",
                {"body": body, "client_id": str(uuid.uuid4())},
                format="json",
            )
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_source_revoke_removes_previous_commenter_from_later_activity_delivery(self):
        self._comment(self.member, "I can see this now")
        Notification.objects.filter(recipient=self.member_membership).delete()

        self.share.delete()
        self._comment(self.owner, "Activity after access was revoked")

        self.assertFalse(
            Notification.objects.filter(
                recipient=self.member_membership,
                event_type="pin.comment",
            ).exists()
        )

    def test_notification_copy_never_contains_pin_or_comment_content(self):
        self._comment(self.member, "Very sensitive comment body")
        row = Notification.objects.filter(
            recipient=self.owner_membership,
            event_type="pin.comment",
        ).latest("created_at")
        rendered = f"{row.title} {row.body}"
        self.assertNotIn("Sensitive pin caption", rendered)
        self.assertNotIn("Private source", rendered)
        self.assertNotIn("Very sensitive comment body", rendered)

    def test_queued_activity_revalidates_source_acl_at_actual_delivery(self):
        from .notification_digests import enqueue_notification, flush_notification_batches
        from .models_features import NotificationBatch
        comment = self._comment(self.owner, 'Queued private discussion')
        enqueue_notification(self.member_membership, 'pin.comment', {'pin_id': self.pin.id, 'comment_id': comment.data['id']})
        self.share.delete()
        with patch('family.notification_digests.send_user_push') as send:
            result = flush_notification_batches(now=timezone.now() + timedelta(minutes=2))
        send.assert_not_called()
        self.assertEqual(result, {'sent': 0, 'errors': 0})
        self.assertFalse(NotificationBatch.objects.filter(membership=self.member_membership).exists())

    def test_queued_mute_suppresses_activity_but_not_direct_mention(self):
        from .notification_digests import enqueue_notification, flush_notification_batches
        from .board_models import PinInteractionState
        comment = self._comment(self.owner, 'Comment')
        context = {'pin_id': self.pin.id, 'comment_id': comment.data['id']}
        PinInteractionState.objects.create(pin=self.pin, membership=self.member_membership, muted=True)
        enqueue_notification(self.member_membership, 'pin.comment', context)
        with patch('family.notification_digests.send_user_push', return_value={'sent': 1, 'errors': 0}) as send:
            flush_notification_batches(now=timezone.now() + timedelta(minutes=2))
            send.assert_not_called()
            enqueue_notification(self.member_membership, 'pin.mention', context)
            flush_notification_batches(now=timezone.now() + timedelta(minutes=2))
            send.assert_called_once()

    def test_queue_keeps_distinct_pin_contexts_without_private_contents(self):
        from .notification_digests import enqueue_notification
        from .models_features import NotificationBatch
        second = BoardPost.objects.create(family=self.family, author=self.owner, text='Other sensitive caption')
        enqueue_notification(self.member_membership, 'pin.mention', {'pin_id': self.pin.id})
        enqueue_notification(self.member_membership, 'pin.mention', {'pin_id': second.id})
        batches = list(NotificationBatch.objects.filter(membership=self.member_membership))
        self.assertEqual(len(batches), 2)
        self.assertNotIn('sensitive', str([row.events for row in batches]).lower())
