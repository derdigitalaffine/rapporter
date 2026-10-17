from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList
from .shopping_learned_order import learned_order_for_store
from .shopping_models import ShoppingSession, ShoppingSessionActivity, ShoppingStore
from .shopping_session_service import record_shopping_item_activity


class ShoppingLearnedOrderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="learned-order-owner", password="x")
        self.outsider = User.objects.create_user(username="learned-order-outsider", password="x")
        self.family = Family.objects.create(name="Learned Order Family", slug="learned-order-family")
        self.other_family = Family.objects.create(name="Other Learned Family", slug="other-learned-family")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER)
        self.shopping_list = ShoppingList.objects.create(family=self.family, name="Groceries")
        self.items = [
            ShoppingItem.objects.create(shopping_list=self.shopping_list, name="Apples", position=30, added_by=self.owner),
            ShoppingItem.objects.create(shopping_list=self.shopping_list, name="Bread", position=20, added_by=self.owner),
            ShoppingItem.objects.create(shopping_list=self.shopping_list, name="Milk", position=10, added_by=self.owner),
        ]
        self.store = ShoppingStore.objects.create(family=self.family, name="Market", created_by=self.owner)
        self.other_store = ShoppingStore.objects.create(family=self.family, name="Other Market", created_by=self.owner)
        self.cross_family_store = ShoppingStore.objects.create(family=self.other_family, name="Foreign", created_by=self.outsider)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _completed_session(self, store=None):
        return ShoppingSession.objects.create(
            family=self.family,
            shopping_list=self.shopping_list,
            status=ShoppingSession.Status.COMPLETED,
            completed_by=self.owner,
            snapshot={"confirmed_store": {"id": str((store or self.store).id)}},
        )

    def _path(self, session, stream, names, server_sequences):
        for client_sequence, (name, server_sequence) in enumerate(zip(names, server_sequences), start=1):
            ShoppingSessionActivity.objects.create(
                session=session,
                sequence=server_sequence,
                kind=ShoppingSessionActivity.Kind.ITEM_CHECKED,
                item_name=name,
                actor=self.owner,
                client_stream=stream,
                client_sequence=client_sequence,
            )

    def test_two_device_paths_ignore_reversed_server_receipt_order(self):
        first = self._completed_session()
        second = self._completed_session()
        self._path(first, "device-a", ["Apples", "Bread", "Milk"], [90, 10, 50])
        self._path(second, "device-b", ["Apples", "Bread", "Milk"], [3, 2, 1])

        result = learned_order_for_store(self.store, self.shopping_list.items.all())

        self.assertEqual(result["source"], "learned")
        self.assertEqual([row["name"] for row in result["ordered_items"]], ["Apples", "Bread", "Milk"])
        self.assertEqual(result["evidence"]["streams"], 2)
        self.assertGreater(result["confidence"], 0)

    def test_retry_is_idempotent_for_same_stream_sequence_and_mutation(self):
        retry_list = ShoppingList.objects.create(family=self.family, name="Retry")
        item = ShoppingItem.objects.create(shopping_list=retry_list, name="Rice", added_by=self.owner)
        ShoppingSession.objects.create(family=self.family, shopping_list=retry_list, started_by=self.owner)
        metadata = {
            "stream": "device-retry",
            "sequence": 1,
            "mutation_id": "d18fac5e-3906-4d55-9335-4c4716ce3478",
        }

        first = record_shopping_item_activity(item, ShoppingSessionActivity.Kind.ITEM_CHECKED, self.owner, metadata)
        second = record_shopping_item_activity(item, ShoppingSessionActivity.Kind.ITEM_CHECKED, self.owner, metadata)

        self.assertEqual(first.id, second.id)
        self.assertEqual(ShoppingSessionActivity.objects.filter(session=first.session).count(), 1)
        first.session.refresh_from_db()
        self.assertEqual(first.session.activity_seq, 1)

    def test_patch_accepts_client_activity_without_treating_it_as_item_field(self):
        session = ShoppingSession.objects.create(
            family=self.family,
            shopping_list=self.shopping_list,
            started_by=self.owner,
        )
        metadata = {
            "stream": "store-device",
            "sequence": 7,
            "mutation_id": "0a0d1adb-5ab0-44f8-94da-217228074462",
        }

        response = self.client.patch(
            f"/api/shopping-items/{self.items[0].id}/",
            {"checked": True, "client_activity": metadata},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.items[0].refresh_from_db()
        self.assertTrue(self.items[0].checked)
        activity = ShoppingSessionActivity.objects.get(session=session)
        self.assertEqual(activity.kind, ShoppingSessionActivity.Kind.ITEM_CHECKED)
        self.assertEqual(activity.client_stream, "store-device")
        self.assertEqual(activity.client_sequence, 7)
        self.assertEqual(str(activity.mutation_id), metadata["mutation_id"])

        retry = self.client.patch(
            f"/api/shopping-items/{self.items[0].id}/",
            {"checked": True, "client_activity": metadata},
            format="json",
        )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(ShoppingSessionActivity.objects.filter(session=session).count(), 1)

    def test_store_evidence_is_isolated_and_insufficient_evidence_falls_back(self):
        first = self._completed_session(self.store)
        second = self._completed_session(self.store)
        self._path(first, "a", ["Apples", "Bread"], [1, 2])
        self._path(second, "b", ["Apples", "Bread"], [2, 1])

        other = learned_order_for_store(self.other_store, self.shopping_list.items.all())

        self.assertEqual(other["source"], "legacy")
        self.assertEqual([row["name"] for row in other["ordered_items"]], ["Milk", "Bread", "Apples"])

        lonely_store = ShoppingStore.objects.create(family=self.family, name="Lonely", created_by=self.owner)
        lone = self._completed_session(lonely_store)
        self._path(lone, "only-device", ["Apples", "Bread", "Milk"], [3, 1, 2])
        fallback = learned_order_for_store(lonely_store, self.shopping_list.items.all())
        self.assertEqual(fallback["source"], "legacy")

    def test_cancelled_or_unconfirmed_sessions_do_not_contribute(self):
        cancelled = ShoppingSession.objects.create(
            family=self.family,
            shopping_list=self.shopping_list,
            status=ShoppingSession.Status.CANCELLED,
            snapshot={"confirmed_store": {"id": str(self.store.id)}},
        )
        unconfirmed = ShoppingSession.objects.create(
            family=self.family,
            shopping_list=self.shopping_list,
            status=ShoppingSession.Status.COMPLETED,
            snapshot={},
        )
        self._path(cancelled, "cancelled", ["Apples", "Bread"], [1, 2])
        self._path(unconfirmed, "unconfirmed", ["Apples", "Bread"], [1, 2])

        result = learned_order_for_store(self.store, self.shopping_list.items.all())
        self.assertEqual(result["source"], "legacy")
        self.assertEqual(result["evidence"]["streams"], 0)

    def test_conflicting_cycle_is_deterministic(self):
        paths = [
            ("cycle-a", ["Apples", "Bread"]),
            ("cycle-b", ["Bread", "Milk"]),
            ("cycle-c", ["Milk", "Apples"]),
        ]
        for index, (stream, names) in enumerate(paths, start=1):
            session = self._completed_session()
            self._path(session, stream, names, [20 + index, 10 + index])

        first = learned_order_for_store(self.store, self.shopping_list.items.all())
        second = learned_order_for_store(self.store, self.shopping_list.items.all())
        self.assertEqual(first["source"], "learned")
        self.assertEqual(first["ordered_items"], second["ordered_items"])
        self.assertEqual([row["name"] for row in first["ordered_items"]], ["Apples", "Bread", "Milk"])

    def test_endpoint_enforces_store_and_list_family_acl_and_reports_source(self):
        first = self._completed_session()
        second = self._completed_session()
        self._path(first, "api-a", ["Apples", "Bread", "Milk"], [5, 4, 3])
        self._path(second, "api-b", ["Apples", "Bread", "Milk"], [9, 8, 7])

        response = self.client.get(
            f"/api/shopping-stores/{self.store.id}/learned-order/?shopping_list={self.shopping_list.id}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["source"], "learned")
        self.assertIn("confidence", response.data)

        forbidden_store = self.client.get(
            f"/api/shopping-stores/{self.cross_family_store.id}/learned-order/?shopping_list={self.shopping_list.id}"
        )
        self.assertEqual(forbidden_store.status_code, 404)

        foreign_list = ShoppingList.objects.create(family=self.other_family, name="Foreign list")
        forbidden_list = self.client.get(
            f"/api/shopping-stores/{self.store.id}/learned-order/?shopping_list={foreign_list.id}"
        )
        self.assertEqual(forbidden_list.status_code, 404)