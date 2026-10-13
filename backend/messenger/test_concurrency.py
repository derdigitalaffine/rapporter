"""PostgreSQL row-lock regressions; SQLite cannot exercise these guarantees."""
import uuid
from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import get_user_model
from django.db import close_old_connections, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature

from auth_identity.service import create_primary_identity
from family.models import Family, Membership
from .invitations import accept_invitation, create_invitation, invitation_token, resolve_invitation
from .models import ChatMessage, Friendship
from .services import direct_conversation, send_message


@skipUnlessDBFeature("has_select_for_update")
class MessengerConcurrencyTests(TransactionTestCase):
    def setUp(self):
        family = Family.objects.create(name="Race", slug="chat-race")
        self.one = get_user_model().objects.create_user(username="race-one", email="race-one@example.com")
        self.two = get_user_model().objects.create_user(username="race-two", email="race-two@example.com")
        for user in (self.one, self.two):
            create_primary_identity(user, user.email, verified=True)
            Membership.objects.create(family=family, user=user, role="adult")

    def parallel(self, callback):
        def run(_):
            close_old_connections()
            try:
                return callback()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(run, [0, 1]))

    def test_same_mailbox_acceptance_creates_one_friendship(self):
        token = invitation_token(create_invitation(self.one, self.two.email, uuid.uuid4()))
        def accept():
            with transaction.atomic():
                invite = resolve_invitation(token, lock=True)
                user = get_user_model().objects.get(pk=self.two.pk)
                return accept_invitation(invite, user).pk
        ids = self.parallel(accept)
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Friendship.objects.count(), 1)
        self.assertEqual(Membership.objects.filter(user=self.two).count(), 1)

    def test_duplicate_send_commits_only_one_message_and_revision(self):
        friend = Friendship.objects.create(low_user=self.one, high_user=self.two)
        member = direct_conversation(self.one, friend.pk)
        request_id = uuid.uuid4()
        def send():
            user = get_user_model().objects.get(pk=self.one.pk)
            return send_message(user, member.conversation_id, client_id=request_id, body="Once").pk
        ids = self.parallel(send)
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(ChatMessage.objects.count(), 1)
        member.conversation.refresh_from_db()
        self.assertEqual(member.conversation.revision, 1)


    def test_opposite_incoming_invites_use_consistent_user_lock_order(self):
        from rest_framework.test import APIClient
        invites = [create_invitation(self.one, self.two.email, uuid.uuid4()), create_invitation(self.two, self.one.email, uuid.uuid4())]
        def accept(index):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(get_user_model().objects.get(pk=self.two.pk if index == 0 else self.one.pk))
                response = client.post(f"/api/chat/invitations/{invites[index].pk}/", {"action": "accept"}, format="json")
                return response.status_code, response.data
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(accept, [0, 1]))
        self.assertEqual([status for status, _ in results], [200, 200], results)
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(Friendship.objects.count(), 1)


    def test_acceptance_racing_block_never_restores_blocked_friendship(self):
        from rest_framework.test import APIClient
        from messenger.models import ChatBlock
        friend = Friendship.objects.create(low_user=self.one, high_user=self.two)
        invite = create_invitation(self.one, self.two.email, uuid.uuid4())
        def action(index):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(get_user_model().objects.get(pk=self.one.pk if index == 0 else self.two.pk))
                path = f"/api/chat/contacts/{friend.pk}/" if index == 0 else f"/api/chat/invitations/{invite.pk}/"
                response = client.post(path, {"action": "block" if index == 0 else "accept"}, format="json")
                return response.status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(action, [0, 1]))
        self.assertEqual(results[0], 200)
        self.assertIn(results[1], [200, 403, 404])
        friend.refresh_from_db()
        self.assertFalse(friend.active)
        self.assertTrue(ChatBlock.objects.filter(blocker=self.one, blocked=self.two).exists())
