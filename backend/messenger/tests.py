import io
import uuid
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from auth_identity.service import create_primary_identity
from family.models import Family, Membership
from mailing.models import TransactionalEmail
from mailing.service import process_one_transactional_email, render_transactional_email
from notifications.models import Notification
from notifications.services import record_personal_notification
from .access import eligible
from .invitations import create_invitation, invitation_token
from .models import ChatMessage, ContactInvitation, ConversationMember, Friendship


class MessengerTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="One", slug="chat-one")
        self.other_family = Family.objects.create(name="Two", slug="chat-two")
        self.one = self.user("one", self.family)
        self.two = self.user("two", self.other_family)
        self.outsider = self.user("outsider", self.family, "owner")
        self.child = self.user("child", self.family, "child")
        self.client = APIClient()
        self.client.force_authenticate(self.one)
        self.friend = Friendship.objects.create(low_user=self.one, high_user=self.two)
        self.conv = self.post("conversations/", {"kind": "direct", "friendship_id": str(self.friend.pk)}).data["id"]

    def user(self, name, family=None, role="adult", verified=True):
        u = get_user_model().objects.create_user(username=name, email=f"{name}@example.com", password="unique-password-42")
        create_primary_identity(u, u.email, verified=verified)
        if family:
            Membership.objects.create(user=u, family=family, role=role, display_name=name)
        return u

    def post(self, route, data):
        return self.client.post("/api/chat/" + route, data, format="json")

    def send(self, body="hello", **extra):
        return self.post(f"conversations/{self.conv}/messages/", {"client_id": str(uuid.uuid4()), "body": body, **extra})

    def test_direct_consent_idempotent_and_family_owner_is_not_participant(self):
        retry = self.post("conversations/", {"kind": "direct", "friendship_id": str(self.friend.pk)})
        self.assertEqual(retry.data["id"], self.conv)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/api/chat/conversations/{self.conv}/messages/").status_code, 404)
        self.assertEqual(self.send().status_code, 404)
        self.assertEqual(self.post("conversations/", {"kind": "direct", "friendship_id": str(self.friend.pk)}).status_code, 404)

    def test_message_retry_edit_delta_reply_tombstone_and_sender_rights(self):
        key = str(uuid.uuid4())
        msg = self.send("secret", client_id=key)
        self.assertEqual(msg.status_code, 201)
        retry = self.send("secret", client_id=key)
        self.assertEqual(retry.data["id"], msg.data["id"])
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertEqual(self.send("different", client_id=key).status_code, 400)
        route = f'/api/chat/conversations/{self.conv}/messages/{msg.data["id"]}/'
        edited = self.client.patch(route, {"body": "edited"}, format="json")
        self.assertEqual(edited.status_code, 200)
        delta = self.client.get(f'/api/chat/conversations/{self.conv}/messages/?after={msg.data["event_sequence"]}')
        self.assertEqual(delta.data["results"][0]["body"], "edited")
        self.client.force_authenticate(self.two)
        self.assertEqual(self.client.delete(route).status_code, 403)
        self.assertEqual(self.client.patch(route, {"reaction": "❤️"}, format="json").status_code, 200)
        reply = self.send("reply", reply_to=msg.data["id"])
        self.assertEqual(reply.data["reply"]["body"], "edited")
        self.client.force_authenticate(self.one)
        self.assertEqual(self.client.delete(route).status_code, 200)
        self.client.force_authenticate(self.two)
        rows = self.client.get(f"/api/chat/conversations/{self.conv}/messages/").data["results"]
        self.assertEqual(rows[0]["body"], "")
        self.assertEqual(rows[0]["reactions"], [])
        self.assertTrue(rows[1]["reply"]["deleted"])

    def test_child_unverified_guest_and_personal_without_consent_cannot_write(self):
        for user in (self.child, self.user("guest", self.family, "guest"), self.user("unverified", self.family, verified=False), self.user("lonely")):
            self.assertFalse(eligible(user))
            self.client.force_authenticate(user)
            self.assertEqual(self.post("invitations/", {"email": "x@example.com", "request_id": str(uuid.uuid4())}).status_code, 403)

    def test_invitation_mail_has_no_persisted_token_and_binds_exact_verified_email(self):
        invite = create_invitation(self.one, self.two.email, uuid.uuid4())
        outbox = TransactionalEmail.objects.get(reference_type="chat.invitation")
        self.assertNotIn("token", str(outbox.context))
        _, text, _ = render_transactional_email(outbox)
        self.assertIn("#chat-invite=", text)
        token = invitation_token(invite)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.post("invite/accept/", {"token": token}).status_code, 404)
        self.client.force_authenticate(self.two)
        accepted = self.post("invite/accept/", {"token": token})
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(self.post("invite/accept/", {"token": token}).data, accepted.data)
        self.assertEqual(Membership.objects.filter(user=self.two).count(), 1)
        self.assertFalse(Membership.objects.filter(user=self.two, family=self.family).exists())

    def test_invited_registration_creates_only_personal_account_and_session(self):
        invite = create_invitation(self.one, "new@example.com", uuid.uuid4())
        self.client.force_authenticate(None)
        response = self.post("invite/register/", {"token": invitation_token(invite), "password": "Correct-Horse-4218!", "display_name": "New Friend"})
        self.assertEqual(response.status_code, 201, response.data)
        u = get_user_model().objects.get(pk=response.data["user_id"])
        self.assertTrue(eligible(u))
        self.assertFalse(Membership.objects.filter(user=u).exists())
        self.assertTrue(response.cookies)
        self.assertEqual(self.post("invite/register/", {"token": invitation_token(invite), "password": "Correct-Horse-4218!", "display_name": "New Friend"}).status_code, 404)

    def test_removed_friendship_blocks_send_typing_and_old_invite_replay(self):
        invite = create_invitation(self.one, self.two.email, uuid.uuid4())
        self.client.force_authenticate(self.two)
        self.post("invite/accept/", {"token": invitation_token(invite)})
        self.client.force_authenticate(self.one)
        self.send()
        self.post(f"contacts/{self.friend.pk}/", {"action": "remove"})
        self.assertEqual(self.send().status_code, 404)
        self.assertEqual(self.post(f"conversations/{self.conv}/typing/", {"active": True}).status_code, 404)
        self.assertEqual(self.client.get(f"/api/chat/conversations/{self.conv}/messages/").status_code, 200)
        self.client.force_authenticate(self.two)
        self.assertEqual(self.post("invite/accept/", {"token": invitation_token(invite)}).status_code, 403)

    def test_block_revokes_queued_mail_and_hides_messages_and_presence(self):
        invite = create_invitation(self.one, self.two.email, uuid.uuid4())
        self.send("private content")
        self.post(f"conversations/{self.conv}/typing/", {"active": True})
        self.client.force_authenticate(self.two)
        self.post(f"contacts/{self.friend.pk}/", {"action": "block"})
        messages = self.client.get(f"/api/chat/conversations/{self.conv}/messages/")
        self.assertEqual(messages.data["results"], [])
        self.assertEqual(messages.data["conversation"]["typing"], [])
        with patch("django.core.mail.EmailMultiAlternatives.send") as send:
            self.assertTrue(process_one_transactional_email())
            send.assert_not_called()
        self.assertEqual(self.post("invite/accept/", {"token": invitation_token(invite)}).status_code, 404)

    def test_typing_ttl_and_read_receipt_preference(self):
        msg = self.send()
        self.post(f"conversations/{self.conv}/typing/", {"active": True})
        self.client.force_authenticate(self.two)
        detail = self.client.get(f"/api/chat/conversations/{self.conv}/").data
        self.assertEqual(len(detail["typing"]), 1)
        ConversationMember.objects.filter(conversation_id=self.conv, user=self.one).update(typing_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(f"/api/chat/conversations/{self.conv}/").data["typing"], [])
        self.post(f"conversations/{self.conv}/read/", {"sequence": msg.data["sequence"]})
        self.client.patch("/api/chat/account/", {"read_receipts": False}, format="json")
        self.client.force_authenticate(self.one)
        self.assertEqual(self.client.get(f"/api/chat/conversations/{self.conv}/").data["read_receipts"], [])

    def test_group_consent_limits_history_and_leave_is_readonly(self):
        group = self.post("conversations/", {"kind": "group", "title": "Friends", "friends": [str(self.friend.pk)]}).data["id"]
        old = self.conv
        self.conv = group
        self.send("before joining")
        self.client.force_authenticate(self.two)
        self.assertEqual(self.client.get(f"/api/chat/conversations/{group}/messages/").data["results"], [])
        self.assertEqual(self.send().status_code, 403)
        self.assertEqual(self.post(f"conversations/{group}/", {"action": "join"}).status_code, 200)
        self.send("joined")
        self.post(f"conversations/{group}/", {"action": "leave"})
        self.assertEqual(self.send().status_code, 403)
        self.assertEqual(len(self.client.get(f"/api/chat/conversations/{group}/messages/").data["results"]), 1)
        self.conv = old

    def test_attachment_download_requires_visible_message_and_delete_revokes_it(self):
        image = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(image, "PNG")
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(f"/api/chat/conversations/{self.conv}/messages/", {"client_id": str(uuid.uuid4()), "body": "photo", "files": SimpleUploadedFile("test.png", image.getvalue(), content_type="image/png")}, format="multipart")
            self.assertEqual(response.status_code, 201, response.data)
            attachment = response.data["attachments"][0]
            self.assertEqual(attachment["mime_type"], "image/webp")
            self.client.force_authenticate(self.outsider)
            self.assertEqual(self.client.get(attachment["url"]).status_code, 404)
            self.client.force_authenticate(self.two)
            downloaded = self.client.get(attachment["url"])
            self.assertEqual(downloaded.status_code, 200)
            self.assertEqual(downloaded["Cache-Control"], "private, no-store")
            downloaded.close()
            self.client.force_authenticate(self.one)
            self.client.delete(f'/api/chat/conversations/{self.conv}/messages/{response.data["id"]}/')
            self.assertEqual(self.client.get(attachment["url"]).status_code, 404)

    def test_personal_notifications_have_no_family_or_message_content(self):
        self.send("DO NOT PUSH THIS")
        with patch("messenger.delivery.send_user_push") as push:
            from .delivery import notify_message
            notify_message(ChatMessage.objects.get().pk)
            self.assertNotIn("DO NOT PUSH", str(push.call_args))
        notification = Notification.objects.get(recipient_user=self.two)
        self.assertIsNone(notification.family_id)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.patch(f"/api/notifications/{notification.pk}/", {"read": True}, format="json").status_code, 404)
        self.client.force_authenticate(self.two)
        self.assertEqual(self.client.get("/api/notifications/").data["results"][0]["family"], None)
        self.assertEqual(self.client.patch(f"/api/notifications/{notification.pk}/", {"read": True}, format="json").status_code, 200)

    def test_scope_constraint_prevents_family_plus_personal_recipient(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notification.objects.create(family=self.family, recipient_user=self.two, title="bad", event_type="chat.message")

    def test_expired_revoked_forged_and_wrong_mailbox_tokens_fail_closed(self):
        invite = create_invitation(self.one, self.two.email, uuid.uuid4())
        token = invitation_token(invite)
        self.client.force_authenticate(self.two)
        self.assertEqual(self.post("invite/accept/", {"token": token + "forged"}).status_code, 404)
        ContactInvitation.objects.filter(pk=invite.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post("invite/accept/", {"token": token}).status_code, 404)
        ContactInvitation.objects.filter(pk=invite.pk).update(expires_at=timezone.now() + timedelta(days=1), status="revoked")
        self.assertEqual(self.post("invite/accept/", {"token": token}).status_code, 404)

    def test_group_replies_cannot_reference_hidden_prejoin_messages_or_another_chat(self):
        old_message = self.send("private before joining").data["id"]
        group = self.post("conversations/", {"kind": "group", "title": "Group", "friends": [str(self.friend.pk)]}).data["id"]
        old = self.conv
        self.conv = group
        group_message = self.send("prejoin").data["id"]
        self.client.force_authenticate(self.two)
        self.post(f"conversations/{group}/", {"action": "join"})
        self.assertEqual(self.send("invalid reply", reply_to=group_message).status_code, 404)
        self.assertEqual(self.send("cross chat", reply_to=old_message).status_code, 404)
        self.conv = old

    def test_role_and_identity_revocation_stop_existing_chat_access(self):
        self.send()
        Membership.objects.filter(user=self.two).update(role="child")
        self.assertEqual(self.send().status_code, 404)
        self.client.force_authenticate(self.two)
        self.assertEqual(self.client.get(f"/api/chat/conversations/{self.conv}/messages/").status_code, 403)

    def test_private_upload_limits_and_html_are_rejected(self):
        route = f"/api/chat/conversations/{self.conv}/messages/"
        html = SimpleUploadedFile("attack.html", b"<html><script>alert(1)</script></html>", content_type="image/png")
        response = self.client.post(route, {"client_id": str(uuid.uuid4()), "body": "attachment", "files": html}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ChatMessage.objects.exists())
        response = self.client.post(route, {"client_id": str(uuid.uuid4()), "body": "attachment", "files": [SimpleUploadedFile(str(i), b"invalid") for i in range(6)]}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_personal_notifications_do_not_expand_other_family_scope(self):
        from notifications.services import record_notification
        own = record_personal_notification(user=self.two, event_type="chat.message", title="New message")[0]
        foreign_member = Membership.objects.get(user=self.one)
        record_notification(recipient=foreign_member, event_type="task.created", title="Family private")
        self.client.force_authenticate(self.two)
        response = self.client.get(f"/api/notifications/?family={self.other_family.pk}")
        self.assertEqual([r["id"] for r in response.data["results"]], [str(own.pk)])
        self.assertEqual(self.client.get(f"/api/notifications/?family={self.family.pk}").status_code, 404)


    def test_read_chat_clears_only_own_matching_personal_notification(self):
        from notifications.services import record_notification
        msg = self.send()
        from .delivery import notify_message
        notify_message(msg.data["id"])
        own = Notification.objects.get(recipient_user=self.two)
        unrelated = record_personal_notification(user=self.two, event_type="chat.message", title="Other chat", resource_url="/?page=inbox&chat=other")[0]
        member = Membership.objects.get(user=self.two)
        family = record_notification(recipient=member, event_type="task.created", title="Family")[0]
        self.client.force_authenticate(self.two)
        response = self.post(f"conversations/{self.conv}/read/", {"sequence": msg.data["sequence"]})
        self.assertEqual(response.status_code, 200)
        own.refresh_from_db(); unrelated.refresh_from_db(); family.refresh_from_db()
        self.assertIsNotNone(own.read_at)
        self.assertIsNone(unrelated.read_at)
        self.assertIsNone(family.read_at)


    def test_pending_invite_from_before_removal_cannot_reactivate_friendship(self):
        invite = create_invitation(self.one, self.two.email, uuid.uuid4())
        self.post(f"contacts/{self.friend.pk}/", {"action": "remove"})
        # TestCase deliberately leaves on_commit cleanup pending, exercising the consent fence itself.
        self.client.force_authenticate(self.two)
        self.assertEqual(self.post("invite/accept/", {"token": invitation_token(invite)}).status_code, 403)
        self.friend.refresh_from_db()
        self.assertFalse(self.friend.active)
        self.client.force_authenticate(self.one)
        fresh = create_invitation(self.one, self.two.email, uuid.uuid4())
        self.client.force_authenticate(self.two)
        self.assertEqual(self.post("invite/accept/", {"token": invitation_token(fresh)}).status_code, 200)


    def test_superadmin_flag_never_grants_personal_chat_access(self):
        self.one.is_superuser = True
        self.one.save(update_fields=["is_superuser"])
        self.client.force_authenticate(self.one)
        self.assertFalse(eligible(self.one))
        response = self.post("invitations/", {"email": self.two.email, "request_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 403)


    def test_personal_chat_does_not_depend_on_family_service_status(self):
        self.family.status = Family.Status.SUSPENDED
        self.family.save(update_fields=["status"])
        self.assertTrue(eligible(self.one))
        self.assertEqual(self.send("personal, no family content").status_code, 201)
        self.assertIn(self.client.get(f"/api/tasks/?family={self.family.pk}").status_code, [403, 404])

    def test_accepted_personal_profile_survives_leaving_family_without_granting_child_access(self):
        invite = create_invitation(self.one, self.two.email, uuid.uuid4())
        self.client.force_authenticate(self.two)
        self.assertEqual(self.post("invite/accept/", {"token": invitation_token(invite)}).status_code, 200)
        Membership.objects.filter(user=self.two).delete()
        self.assertTrue(eligible(self.two))
        self.assertEqual(self.send("still personal").status_code, 201)
        Membership.objects.create(user=self.two, family=self.other_family, role="child")
        self.assertFalse(eligible(self.two))
        self.assertEqual(self.send().status_code, 403)
