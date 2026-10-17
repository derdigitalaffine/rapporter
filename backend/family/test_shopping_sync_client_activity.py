from uuid import UUID, uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList
from .shopping_models import ShoppingSessionActivity


class ShoppingStoreSyncClientActivityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("store-sync", password="x")
        self.family = Family.objects.create(name="Store Sync", slug="store-sync")
        Membership.objects.create(user=self.user, family=self.family, role=Membership.Role.OWNER)
        self.shopping_list = ShoppingList.objects.create(family=self.family, name="Supermarkt")
        self.item = ShoppingItem.objects.create(shopping_list=self.shopping_list, name="Milch")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_checked_item_sync_accepts_client_activity_and_records_learning_metadata_once(self):
        started = self.client.post(
            "/api/shopping-sessions/start/",
            {"shopping_list": str(self.shopping_list.id)},
            format="json",
        )
        self.assertIn(started.status_code, {200, 201}, started.data)

        mutation_id = str(uuid4())
        activity_id = str(uuid4())
        mutation = {
            "mutation_id": mutation_id,
            "entity_type": "shopping_item",
            "entity_id": str(self.item.id),
            "operation": "update",
            "base_version": self.item.version,
            "changes": {
                "checked": True,
                "client_activity": {
                    "stream": "store-device-a",
                    "sequence": 1,
                    "mutation_id": activity_id,
                },
            },
        }
        payload = {
            "protocol_version": 1,
            "family_id": str(self.family.id),
            "cursor": None,
            "mutations": [mutation],
        }

        response = self.client.post("/api/sync/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        result = response.data["mutation_results"][0]
        self.assertEqual(result["status"], "applied", result)

        self.item.refresh_from_db()
        self.assertTrue(self.item.checked)
        activity = ShoppingSessionActivity.objects.get(
            session_id=started.data["session"]["id"],
            kind=ShoppingSessionActivity.Kind.ITEM_CHECKED,
        )
        self.assertEqual(activity.item_id, self.item.id)
        self.assertEqual(activity.client_stream, "store-device-a")
        self.assertEqual(activity.client_sequence, 1)
        self.assertEqual(activity.mutation_id, UUID(activity_id))

        retried = self.client.post("/api/sync/", payload, format="json")
        self.assertEqual(retried.status_code, 200, retried.data)
        self.assertEqual(retried.data["mutation_results"][0]["status"], "already_applied")
        self.assertEqual(
            ShoppingSessionActivity.objects.filter(
                session_id=started.data["session"]["id"],
                kind=ShoppingSessionActivity.Kind.ITEM_CHECKED,
            ).count(),
            1,
        )
