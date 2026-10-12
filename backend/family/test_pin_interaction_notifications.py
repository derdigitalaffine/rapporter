import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from notifications.models import Notification

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
