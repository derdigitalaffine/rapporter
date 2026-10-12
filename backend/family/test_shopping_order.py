from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList


class ShoppingOrderApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="shopping-order-owner", password="test-pass-123")
        self.other = User.objects.create_user(username="shopping-order-other", password="test-pass-123")
        self.family = Family.objects.create(name="Order Family", slug="order-family")
        self.other_family = Family.objects.create(name="Other Order Family", slug="other-order-family")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other_family, user=self.other, role=Membership.Role.OWNER)
        self.shopping = ShoppingList.objects.create(family=self.family, name="Woche")
        self.items = [ShoppingItem.objects.create(shopping_list=self.shopping, name=name, added_by=self.user) for name in ["Milch", "Brot", "Äpfel"]]
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_reorder_persists_and_nested_list_uses_manual_order(self):
        wanted = [self.items[2], self.items[0], self.items[1]]
        response = self.client.post(
            f"/api/smart/shopping-lists/{self.shopping.id}/reorder/",
            {"item_ids": [str(item.id) for item in wanted]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["name"] for row in response.data], [item.name for item in wanted])

        persisted = list(ShoppingItem.objects.filter(shopping_list=self.shopping))
        self.assertEqual([item.name for item in persisted], [item.name for item in wanted])
        self.assertEqual([item.position for item in persisted], [1000, 2000, 3000])

        nested = self.client.get(f"/api/shopping-lists/{self.shopping.id}/")
        self.assertEqual(nested.status_code, 200, nested.data)
        self.assertEqual([row["name"] for row in nested.data["items"]], [item.name for item in wanted])

    def test_checkoff_does_not_change_manual_position(self):
        self.items[1].position = 1000
        self.items[1].save(update_fields=["position", "updated_at"])
        before = self.items[1].position
        response = self.client.post(f"/api/shopping-items/{self.items[1].id}/toggle/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.items[1].refresh_from_db()
        self.assertTrue(self.items[1].checked)
        self.assertEqual(self.items[1].position, before)

    def test_reorder_requires_complete_unique_visible_sequence(self):
        missing = self.client.post(
            f"/api/smart/shopping-lists/{self.shopping.id}/reorder/",
            {"item_ids": [str(self.items[0].id), str(self.items[1].id)]},
            format="json",
        )
        self.assertEqual(missing.status_code, 400)

        duplicate = self.client.post(
            f"/api/smart/shopping-lists/{self.shopping.id}/reorder/",
            {"item_ids": [str(self.items[0].id), str(self.items[0].id), str(self.items[2].id)]},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)

    def test_reorder_preserves_hidden_item_slot_without_exposing_its_id(self):
        for index, item in enumerate(self.items, start=1):
            item.position = (index * 1000) + (1000 if index > 1 else 0)
            item.save(update_fields=["position", "updated_at"])
        hidden = ShoppingItem.objects.create(
            shopping_list=self.shopping,
            name="Geheimes Geschenk",
            added_by=self.user,
            hidden_from_user=self.user,
            position=2000,
        )
        wanted = [self.items[2], self.items[0], self.items[1]]
        response = self.client.post(
            f"/api/smart/shopping-lists/{self.shopping.id}/reorder/",
            {"item_ids": [str(item.id) for item in wanted]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row["name"] for row in response.data], [item.name for item in wanted])
        self.assertNotIn(str(hidden.id), [str(row["id"]) for row in response.data])

        persisted = list(ShoppingItem.objects.filter(shopping_list=self.shopping))
        self.assertEqual([item.name for item in persisted], ["Äpfel", "Geheimes Geschenk", "Milch", "Brot"])
        self.assertEqual([item.position for item in persisted], [1000, 2000, 3000, 4000])

    def test_reorder_is_family_scoped(self):
        foreign_list = ShoppingList.objects.create(family=self.other_family, name="Foreign")
        foreign_item = ShoppingItem.objects.create(shopping_list=foreign_list, name="Secret", added_by=self.other)
        response = self.client.post(
            f"/api/smart/shopping-lists/{foreign_list.id}/reorder/",
            {"item_ids": [str(foreign_item.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
