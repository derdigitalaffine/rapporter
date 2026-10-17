from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList
from .shopping_models import ShoppingSession, ShoppingSessionParticipant


class ShoppingCheckoutCollaborationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="checkout-collab-owner", password="x")
        self.peer = User.objects.create_user(username="checkout-collab-peer", password="x")
        self.outsider = User.objects.create_user(username="checkout-collab-outsider", password="x")
        self.family = Family.objects.create(name="Checkout Collaboration", slug="checkout-collaboration")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family, user=self.peer, role=Membership.Role.ADULT)
        self.shopping_list = ShoppingList.objects.create(family=self.family, name="Groceries")
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)
        self.peer_client = APIClient()
        self.peer_client.force_authenticate(self.peer)
        self.outsider_client = APIClient()
        self.outsider_client.force_authenticate(self.outsider)

    def _start(self):
        started = self.owner_client.post(
            "/api/shopping-sessions/start/",
            {"shopping_list": str(self.shopping_list.id)},
            format="json",
        )
        self.assertEqual(started.status_code, 201)
        return started.data["session"]["id"]

    def _add_purchase(self):
        return ShoppingItem.objects.create(
            shopping_list=self.shopping_list,
            name="Milk",
            checked=True,
            added_by=self.owner,
        )

    def test_personal_finish_leaves_active_group_session_without_closing_list(self):
        session_id = self._start()
        joined = self.peer_client.post(
            "/api/shopping-sessions/start/",
            {"shopping_list": str(self.shopping_list.id)},
            format="json",
        )
        self.assertEqual(joined.status_code, 200)

        left = self.peer_client.post(
            "/api/shopping-sessions/complete/",
            {"shopping_list": str(self.shopping_list.id), "session": session_id, "scope": "me"},
            format="json",
        )

        self.assertEqual(left.status_code, 200)
        self.assertTrue(left.data["left"])
        self.assertEqual(left.data["session"]["status"], ShoppingSession.Status.ACTIVE)
        self.assertFalse(
            ShoppingSessionParticipant.objects.filter(session_id=session_id, user=self.peer).exists()
        )
        self.assertTrue(
            ShoppingSessionParticipant.objects.filter(session_id=session_id, user=self.owner).exists()
        )
        self.assertEqual(ShoppingSession.objects.get(id=session_id).status, ShoppingSession.Status.ACTIVE)

        retried = self.peer_client.post(
            "/api/shopping-sessions/complete/",
            {"shopping_list": str(self.shopping_list.id), "session": session_id, "scope": "me"},
            format="json",
        )
        self.assertEqual(retried.status_code, 200)
        self.assertTrue(retried.data["left"])

    def test_group_finish_requires_explicit_confirmation_for_active_peer(self):
        session_id = self._start()
        self._add_purchase()
        joined = self.peer_client.post(
            "/api/shopping-sessions/start/",
            {"shopping_list": str(self.shopping_list.id)},
            format="json",
        )
        self.assertEqual(joined.status_code, 200)

        blocked = self.owner_client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "scope": "group",
                "expected_revision": 0,
                "open_items": "keep",
            },
            format="json",
        )

        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data["code"], "active_peers_confirmation_required")
        self.assertEqual([person["id"] for person in blocked.data["participants"]], [self.peer.id])
        self.assertEqual(ShoppingSession.objects.get(id=session_id).status, ShoppingSession.Status.ACTIVE)

        completed = self.owner_client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "scope": "group",
                "expected_revision": 0,
                "confirm_active_peers": True,
                "open_items": "keep",
            },
            format="json",
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["session"]["status"], ShoppingSession.Status.COMPLETED)

    def test_stale_revision_returns_409_without_mutating_checkout(self):
        session_id = self._start()
        item = self._add_purchase()
        ShoppingSession.objects.filter(id=session_id).update(activity_seq=2)

        stale = self.owner_client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "scope": "group",
                "expected_revision": 1,
                "open_items": "keep",
            },
            format="json",
        )

        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data["code"], "stale_session")
        self.assertEqual(stale.data["revision"], 2)
        self.assertEqual(stale.data["session"]["revision"], 2)
        session = ShoppingSession.objects.get(id=session_id)
        self.assertEqual(session.status, ShoppingSession.Status.ACTIVE)
        self.assertEqual(session.snapshot, {})
        self.assertTrue(ShoppingItem.objects.filter(id=item.id).exists())

        completed = self.owner_client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "scope": "group",
                "expected_revision": 2,
                "open_items": "keep",
            },
            format="json",
        )
        self.assertEqual(completed.status_code, 200)

        retry = self.owner_client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "scope": "group",
                "expected_revision": 0,
                "open_items": "remove",
            },
            format="json",
        )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.data["completion"], completed.data["completion"])

    def test_guessed_family_cannot_leave_or_complete_foreign_session(self):
        session_id = self._start()
        hidden = self.outsider_client.post(
            "/api/shopping-sessions/complete/",
            {"shopping_list": str(self.shopping_list.id), "session": session_id, "scope": "me"},
            format="json",
        )
        self.assertEqual(hidden.status_code, 404)
