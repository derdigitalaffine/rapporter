from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .memory import normalize_name
from .models import EntryMemory, Family, Membership, ShoppingItem, ShoppingList, ShoppingPurchaseEvent
from .shopping_models import ShoppingListStoreProfile, ShoppingStore, ShoppingTemplate


class ShoppingTemplateApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="shopping-template-owner", password="test-pass-123")
        self.other = User.objects.create_user(username="shopping-template-other", password="test-pass-123")
        self.family = Family.objects.create(name="Template Family", slug="template-family")
        self.other_family = Family.objects.create(name="Other Template Family", slug="other-template-family")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other_family, user=self.other, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.shopping = ShoppingList.objects.create(family=self.family, name="Wocheneinkauf", store="Altmarkt")

    def _store(self, name="REWE", **extra):
        payload = {"family": str(self.family.id), "name": name, **extra}
        response = self.client.post("/api/shopping-stores/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def _template(self, **extra):
        payload = {
            "family": str(self.family.id),
            "name": "Standard",
            "items": [
                {"name": "Milch", "quantity": "2 l", "category": "Kühlung", "position": 0},
                {"name": "Brot", "quantity": "1", "position": 1},
                {"name": "Eier", "quantity": "10", "position": 2},
            ],
            **extra,
        }
        response = self.client.post("/api/shopping-templates/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_store_urls_are_https_only_and_family_scoped(self):
        bad = self.client.post(
            "/api/shopping-stores/",
            {"family": str(self.family.id), "name": "Unsicher", "offers_url": "http://example.test/offers"},
            format="json",
        )
        self.assertEqual(bad.status_code, 400)

        store = self._store(offers_url="https://example.test/offers")
        other_store = ShoppingStore.objects.create(family=self.other_family, name="Other", created_by=self.other)
        rows = self.client.get(f"/api/shopping-stores/?family={self.family.id}")
        data = rows.data.get("results", rows.data)
        self.assertEqual([row["id"] for row in data], [store["id"]])
        self.assertNotIn(str(other_store.id), [row["id"] for row in data])

    def test_store_assignment_keeps_legacy_store_field_useful(self):
        store = self._store(name="REWE", branch_label="Innenstadt")
        assigned = self.client.post(
            f"/api/shopping-stores/{store['id']}/assign/",
            {"shopping_list": str(self.shopping.id)},
            format="json",
        )
        self.assertEqual(assigned.status_code, 200, assigned.data)
        self.shopping.refresh_from_db()
        self.assertEqual(self.shopping.store, "REWE · Innenstadt")
        self.assertEqual(ShoppingListStoreProfile.objects.get(shopping_list=self.shopping).store_id, store["id"])

        renamed = self.client.patch(
            f"/api/shopping-stores/{store['id']}/",
            {"branch_label": "West"},
            format="json",
        )
        self.assertEqual(renamed.status_code, 200, renamed.data)
        self.shopping.refresh_from_db()
        self.assertEqual(self.shopping.store, "REWE · West")

    def test_template_rejects_cross_family_store_and_duplicate_names(self):
        foreign = ShoppingStore.objects.create(family=self.other_family, name="Foreign", created_by=self.other)
        response = self.client.post(
            "/api/shopping-templates/",
            {
                "family": str(self.family.id),
                "name": "Invalid",
                "default_store": str(foreign.id),
                "items": [{"name": "Milch"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        duplicate = self.client.post(
            "/api/shopping-templates/",
            {
                "family": str(self.family.id),
                "name": "Duplicate",
                "items": [{"name": " Milch "}, {"name": "MILCH"}],
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)

    def test_preview_and_apply_are_non_destructive_idempotent_and_do_not_create_purchase_history(self):
        milk = ShoppingItem.objects.create(shopping_list=self.shopping, name="Milch", added_by=self.user)
        bread = ShoppingItem.objects.create(
            shopping_list=self.shopping,
            name="Brot",
            checked=True,
            checked_at=timezone.now(),
            added_by=self.user,
        )
        extra = ShoppingItem.objects.create(shopping_list=self.shopping, name="Kaffee", note="Bleibt", added_by=self.user)
        self.assertEqual(ShoppingPurchaseEvent.objects.filter(source_item_id=bread.id).count(), 1)
        purchase_count = ShoppingPurchaseEvent.objects.count()
        memory_count = EntryMemory.objects.filter(family=self.family, kind=EntryMemory.Kind.SHOPPING).count()
        template = self._template()

        preview = self.client.get(f"/api/shopping-templates/{template['id']}/preview/?shopping_list={self.shopping.id}")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data, {"created": 1, "reopened": 1, "already_open": 1, "total": 3})

        applied = self.client.post(
            f"/api/shopping-templates/{template['id']}/apply/",
            {"shopping_list": str(self.shopping.id)},
            format="json",
        )
        self.assertEqual(applied.status_code, 200, applied.data)
        self.assertEqual(applied.data["created"], 1)
        self.assertEqual(applied.data["reopened"], 1)
        self.assertEqual(applied.data["already_open"], 1)

        milk.refresh_from_db()
        bread.refresh_from_db()
        extra.refresh_from_db()
        self.assertEqual(milk.quantity, "2 l")
        self.assertFalse(bread.checked)
        self.assertIsNone(bread.checked_at)
        self.assertEqual(extra.note, "Bleibt")
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.shopping, name="Eier", checked=False).count(), 1)
        self.assertEqual(ShoppingPurchaseEvent.objects.count(), purchase_count)
        self.assertEqual(EntryMemory.objects.filter(family=self.family, kind=EntryMemory.Kind.SHOPPING).count(), memory_count)

        repeated = self.client.post(
            f"/api/shopping-templates/{template['id']}/apply/",
            {"shopping_list": str(self.shopping.id)},
            format="json",
        )
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(repeated.data, {"created": 0, "reopened": 0, "already_open": 3, "total": 3})
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.shopping, checked=False).count(), 4)

    def test_reopened_template_item_can_be_purchased_again_normally(self):
        item = ShoppingItem.objects.create(
            shopping_list=self.shopping,
            name="Butter",
            checked=True,
            checked_at=timezone.now(),
            added_by=self.user,
        )
        initial = ShoppingPurchaseEvent.objects.filter(source_item_id=item.id).count()
        template = self.client.post(
            "/api/shopping-templates/",
            {"family": str(self.family.id), "name": "Butter", "items": [{"name": "Butter"}]},
            format="json",
        ).data
        self.client.post(f"/api/shopping-templates/{template['id']}/apply/", {"shopping_list": str(self.shopping.id)}, format="json")

        checked = self.client.patch(f"/api/shopping-items/{item.id}/", {"checked": True}, format="json")
        self.assertEqual(checked.status_code, 200)
        self.assertEqual(ShoppingPurchaseEvent.objects.filter(source_item_id=item.id).count(), initial + 1)

    def test_from_list_copies_content_but_not_runtime_state(self):
        open_item = ShoppingItem.objects.create(shopping_list=self.shopping, name="Tomaten", quantity="500 g", added_by=self.user)
        checked_item = ShoppingItem.objects.create(shopping_list=self.shopping, name="Nudeln", checked=True, checked_at=timezone.now(), added_by=self.user)

        response = self.client.post(
            "/api/shopping-templates/from-list/",
            {"shopping_list": str(self.shopping.id), "name": "Pasta-Abend", "item_ids": [str(open_item.id), str(checked_item.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["item_count"], 2)
        self.assertEqual([row["name"] for row in response.data["items"]], ["Tomaten", "Nudeln"])
        for row in response.data["items"]:
            self.assertNotIn("checked", row)
            self.assertNotIn("added_by", row)

    def test_create_list_uses_default_store_and_normal_items_without_fake_memory(self):
        store = self._store(name="dm", branch_label="Zentrum", offers_url="https://example.test/dm")
        template = self._template(name="Drogerie", default_store=store["id"])
        before_memory = EntryMemory.objects.filter(family=self.family, kind=EntryMemory.Kind.SHOPPING).count()

        response = self.client.post(
            f"/api/shopping-templates/{template['id']}/create-list/",
            {"name": "Samstag"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        created = ShoppingList.objects.get(id=response.data["id"])
        self.assertEqual(created.name, "Samstag")
        self.assertEqual(created.store, "dm · Zentrum")
        self.assertEqual(created.items.count(), 3)
        self.assertEqual(ShoppingListStoreProfile.objects.get(shopping_list=created).store_id, store["id"])
        self.assertEqual(EntryMemory.objects.filter(family=self.family, kind=EntryMemory.Kind.SHOPPING).count(), before_memory)

    def test_cross_family_template_and_target_list_are_not_usable(self):
        template = self._template()
        foreign_list = ShoppingList.objects.create(family=self.other_family, name="Foreign")
        response = self.client.post(
            f"/api/shopping-templates/{template['id']}/apply/",
            {"shopping_list": str(foreign_list.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        foreign_template = ShoppingTemplate.objects.create(family=self.other_family, name="Hidden", created_by=self.other)
        hidden = self.client.get(f"/api/shopping-templates/{foreign_template.id}/")
        self.assertEqual(hidden.status_code, 404)
