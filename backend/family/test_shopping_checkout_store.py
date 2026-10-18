from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList
from .shopping_models import ShoppingSession, ShoppingStore


class ShoppingCheckoutStoreTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="checkout-store-owner", password="x")
        self.outsider = User.objects.create_user(username="checkout-store-outsider", password="x")
        self.family = Family.objects.create(name="Checkout Store Family", slug="checkout-store-family")
        self.other_family = Family.objects.create(name="Other Checkout Store Family", slug="other-checkout-store-family")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER)
        self.shopping_list = ShoppingList.objects.create(
            family=self.family,
            name="Groceries",
            store="Legacy Market",
        )
        self.store = ShoppingStore.objects.create(
            family=self.family,
            name="Market",
            branch_label="Innenstadt",
            address="Marktstraße 1",
            created_by=self.owner,
        )
        self.other_store = ShoppingStore.objects.create(
            family=self.other_family,
            name="Other Market",
            branch_label="Cross family",
            created_by=self.outsider,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _start_with_purchase(self):
        started = self.client.post(
            "/api/shopping-sessions/start/",
            {"shopping_list": str(self.shopping_list.id)},
            format="json",
        )
        self.assertEqual(started.status_code, 201)
        ShoppingItem.objects.create(
            shopping_list=self.shopping_list,
            name="Milk",
            checked=True,
            added_by=self.owner,
        )
        return started.data["session"]["id"]

    def test_completion_snapshots_confirmed_same_family_store(self):
        session_id = self._start_with_purchase()

        response = self.client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "open_items": "keep",
                "store": str(self.store.id),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        confirmed = response.data["completion"]["confirmed_store"]
        self.assertEqual(confirmed["id"], str(self.store.id))
        self.assertEqual(confirmed["name"], "Market")
        self.assertEqual(confirmed["branch_label"], "Innenstadt")
        self.assertEqual(confirmed["address"], "Marktstraße 1")
        self.assertEqual(confirmed["display_label"], "Market · Innenstadt")
        self.assertEqual(response.data["completion"]["shopping_list"]["store"], "Market · Innenstadt")

        session = ShoppingSession.objects.get(id=session_id)
        self.assertEqual(session.snapshot["confirmed_store"]["id"], str(self.store.id))

    def test_completion_rejects_cross_family_store_without_mutating_session(self):
        session_id = self._start_with_purchase()

        response = self.client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "open_items": "keep",
                "store": str(self.other_store.id),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "invalid_store")
        session = ShoppingSession.objects.get(id=session_id)
        self.assertEqual(session.status, ShoppingSession.Status.ACTIVE)
        self.assertEqual(session.snapshot, {})
        self.assertTrue(ShoppingItem.objects.filter(shopping_list=self.shopping_list, name="Milk").exists())

    def test_completion_without_store_remains_supported(self):
        session_id = self._start_with_purchase()

        response = self.client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "open_items": "keep",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["completion"]["confirmed_store"])
        self.assertEqual(response.data["completion"]["shopping_list"]["store"], "Legacy Market")

    def test_completed_retry_keeps_original_confirmed_store(self):
        session_id = self._start_with_purchase()
        completed = self.client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "open_items": "keep",
                "store": str(self.store.id),
            },
            format="json",
        )
        self.assertEqual(completed.status_code, 200)
        original_snapshot = ShoppingSession.objects.get(id=session_id).snapshot

        retried = self.client.post(
            "/api/shopping-sessions/complete/",
            {
                "shopping_list": str(self.shopping_list.id),
                "session": session_id,
                "open_items": "remove",
                "store": str(self.other_store.id),
            },
            format="json",
        )

        self.assertEqual(retried.status_code, 200)
        session = ShoppingSession.objects.get(id=session_id)
        self.assertEqual(session.snapshot, original_snapshot)
        self.assertEqual(retried.data["completion"]["confirmed_store"]["id"], str(self.store.id))
