from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList
from .shopping_learned_order import learned_order_for_store
from .shopping_models import ShoppingListAccess, ShoppingSession, ShoppingSessionActivity, ShoppingStore
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

    def _item(self, name, items=None):
        source_items = self.items if items is None else items
        return next(item for item in source_items if item.name == name)

    def _completed_session(self, store=None, purchased_names=None, shopping_list=None, items=None):
        source_list = shopping_list or self.shopping_list
        source_items = self.items if items is None else items
        names = [item.name for item in source_items] if purchased_names is None else purchased_names
        purchased = [self._item(name, source_items) for name in names]
        return ShoppingSession.objects.create(
            family=self.family,
            shopping_list=source_list,
            status=ShoppingSession.Status.COMPLETED,
            completed_by=self.owner,
            snapshot={
                "confirmed_store": {"id": str((store or self.store).id)},
                "purchased_items": [
                    {"id": str(item.id), "name": item.name}
                    for item in purchased
                ],
            },
        )

    def _activity(self, session, stream, name, kind, client_sequence, server_sequence, items=None):
        item = self._item(name, items)
        return ShoppingSessionActivity.objects.create(
            session=session,
            sequence=server_sequence,
            kind=kind,
            item_id=item.id,
            item_name=name,
            actor=self.owner,
            client_stream=stream,
            client_sequence=client_sequence,
        )

    def _path(self, session, stream, names, server_sequences, items=None):
        for client_sequence, (name, server_sequence) in enumerate(zip(names, server_sequences), start=1):
            self._activity(
                session,
                stream,
                name,
                ShoppingSessionActivity.Kind.ITEM_CHECKED,
                client_sequence,
                server_sequence,
                items,
            )

    def _source_list(self, name, visibility=None):
        shopping_list = ShoppingList.objects.create(family=self.family, name=name)
        items = [
            ShoppingItem.objects.create(shopping_list=shopping_list, name="Apples", position=30, added_by=self.owner),
            ShoppingItem.objects.create(shopping_list=shopping_list, name="Bread", position=20, added_by=self.owner),
            ShoppingItem.objects.create(shopping_list=shopping_list, name="Milk", position=10, added_by=self.owner),
        ]
        if visibility is not None:
            ShoppingListAccess.objects.create(
                shopping_list=shopping_list,
                created_by=self.owner,
                visibility=visibility,
            )
        return shopping_list, items

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

    def test_explicit_family_scope_contributes_to_family_pool(self):
        ShoppingListAccess.objects.create(
            shopping_list=self.shopping_list,
            created_by=self.owner,
            visibility=ShoppingListAccess.Visibility.FAMILY,
        )
        for stream in ["family-a", "family-b"]:
            session = self._completed_session()
            self._path(session, stream, ["Apples", "Bread", "Milk"], [3, 2, 1])

        result = learned_order_for_store(self.store, self.shopping_list.items.all())

        self.assertEqual(result["source"], "learned")
        self.assertEqual(result["evidence"]["streams"], 2)

    def test_private_and_selected_scopes_never_feed_family_pool(self):
        for visibility in [ShoppingListAccess.Visibility.PRIVATE, ShoppingListAccess.Visibility.SELECTED]:
            with self.subTest(visibility=visibility):
                source_list, source_items = self._source_list(f"Scoped {visibility}", visibility)
                first = self._completed_session(shopping_list=source_list, items=source_items)
                second = self._completed_session(shopping_list=source_list, items=source_items)
                self._path(first, f"{visibility}-a", ["Apples", "Bread", "Milk"], [1, 2, 3], source_items)
                self._path(second, f"{visibility}-b", ["Apples", "Bread", "Milk"], [3, 2, 1], source_items)

                result = learned_order_for_store(self.store, self.shopping_list.items.all())

                self.assertEqual(result["source"], "legacy")
                self.assertEqual(result["evidence"]["streams"], 0)

    def test_scope_narrowing_removes_previously_eligible_evidence(self):
        source_list, source_items = self._source_list("Narrowed", ShoppingListAccess.Visibility.FAMILY)
        for stream in ["narrow-a", "narrow-b"]:
            session = self._completed_session(shopping_list=source_list, items=source_items)
            self._path(session, stream, ["Apples", "Bread", "Milk"], [3, 2, 1], source_items)

        before = learned_order_for_store(self.store, self.shopping_list.items.all())
        self.assertEqual(before["source"], "learned")

        access = source_list.access_settings
        access.visibility = ShoppingListAccess.Visibility.SELECTED
        access.save(update_fields=["visibility"])

        after = learned_order_for_store(self.store, self.shopping_list.items.all())
        self.assertEqual(after["source"], "legacy")
        self.assertEqual(after["evidence"]["streams"], 0)

    def test_deleting_source_list_removes_derived_evidence(self):
        source_list, source_items = self._source_list("Disposable")
        source_list_id = source_list.id
        for stream in ["delete-a", "delete-b"]:
            session = self._completed_session(shopping_list=source_list, items=source_items)
            self._path(session, stream, ["Apples", "Bread", "Milk"], [1, 2, 3], source_items)

        before = learned_order_for_store(self.store, self.shopping_list.items.all())
        self.assertEqual(before["source"], "learned")
        self.assertEqual(ShoppingSession.objects.filter(shopping_list_id=source_list_id).count(), 2)

        source_list.delete()

        self.assertFalse(ShoppingSession.objects.filter(shopping_list_id=source_list_id).exists())
        after = learned_order_for_store(self.store, self.shopping_list.items.all())
        self.assertEqual(after["source"], "legacy")
        self.assertEqual(after["evidence"]["streams"], 0)

    def test_parallel_paths_in_one_session_never_create_cross_stream_edges(self):
        frozen = ShoppingItem.objects.create(
            shopping_list=self.shopping_list,
            name="Frozen",
            position=40,
            added_by=self.owner,
        )
        self.items.append(frozen)
        session = self._completed_session()
        self._path(session, "person-a", ["Apples", "Bread"], [40, 10])
        self._path(session, "person-b", ["Milk", "Frozen"], [20, 30])

        result = learned_order_for_store(self.store, self.shopping_list.items.all())

        self.assertEqual(result["source"], "learned")
        self.assertEqual(result["evidence"]["streams"], 2)
        self.assertEqual(result["evidence"]["pair_observations"], 2)

    def test_only_items_in_final_purchase_snapshot_contribute(self):
        for stream in ["purchase-a", "purchase-b"]:
            session = self._completed_session(purchased_names=["Apples", "Bread"])
            self._path(session, stream, ["Apples", "Milk", "Bread"], [1, 2, 3])

        result = learned_order_for_store(self.store, self.shopping_list.items.all())

        self.assertEqual(result["source"], "learned")
        self.assertEqual([row["name"] for row in result["ordered_items"]], ["Apples", "Bread", "Milk"])
        self.assertEqual(result["evidence"]["streams"], 2)
        self.assertEqual(result["evidence"]["pair_observations"], 2)

    def test_reopen_and_recheck_use_terminal_client_position(self):
        for stream in ["recheck-a", "recheck-b"]:
            session = self._completed_session()
            self._activity(session, stream, "Apples", ShoppingSessionActivity.Kind.ITEM_CHECKED, 1, 90)
            self._activity(session, stream, "Bread", ShoppingSessionActivity.Kind.ITEM_CHECKED, 2, 10)
            self._activity(session, stream, "Apples", ShoppingSessionActivity.Kind.ITEM_REOPENED, 3, 80)
            self._activity(session, stream, "Apples", ShoppingSessionActivity.Kind.ITEM_CHECKED, 4, 20)
            self._activity(session, stream, "Milk", ShoppingSessionActivity.Kind.ITEM_CHECKED, 5, 70)

        result = learned_order_for_store(self.store, self.shopping_list.items.all())

        self.assertEqual(result["source"], "learned")
        self.assertEqual([row["name"] for row in result["ordered_items"]], ["Bread", "Apples", "Milk"])
        self.assertEqual(result["evidence"]["streams"], 2)
        self.assertEqual(result["evidence"]["pair_observations"], 4)

    def test_legacy_completed_session_without_purchase_snapshot_does_not_contribute(self):
        session = ShoppingSession.objects.create(
            family=self.family,
            shopping_list=self.shopping_list,
            status=ShoppingSession.Status.COMPLETED,
            completed_by=self.owner,
            snapshot={"confirmed_store": {"id": str(self.store.id)}},
        )
        self._path(session, "legacy", ["Apples", "Bread", "Milk"], [1, 2, 3])

        result = learned_order_for_store(self.store, self.shopping_list.items.all())

        self.assertEqual(result["source"], "legacy")
        self.assertEqual(result["evidence"]["streams"], 0)

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
