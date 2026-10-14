from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .context_links import ContextRef, default_context_registry
from .models import EntryMemory, Family, Membership, ShoppingItem, ShoppingList, ShoppingPurchaseEvent
from .shopping_access import can_manage_shopping_access, shopping_notification_user_ids
from .shopping_models import ShoppingListAccess


class ShoppingListAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="shop-owner", password="x")
        self.teen = User.objects.create_user(username="shop-teen", password="x")
        self.other_adult = User.objects.create_user(username="shop-adult", password="x")
        self.outsider = User.objects.create_user(username="shop-outsider", password="x")
        self.family = Family.objects.create(name="Shop Family", slug="shop-family")
        self.other_family = Family.objects.create(name="Other Shop Family", slug="other-shop-family")
        self.owner_member = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        self.teen_member = Membership.objects.create(family=self.family, user=self.teen, role=Membership.Role.TEEN, display_name="Teen")
        self.adult_member = Membership.objects.create(family=self.family, user=self.other_adult, role=Membership.Role.ADULT, display_name="Adult")
        self.outside_member = Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER, display_name="Outside")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def rows(self, response):
        return response.data.get("results", response.data)

    def test_legacy_list_remains_family_visible_but_only_adults_manage_access(self):
        legacy = ShoppingList.objects.create(family=self.family, name="Legacy")
        teen_client = APIClient(); teen_client.force_authenticate(self.teen)
        response = teen_client.get("/api/shopping-lists/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(legacy.id), {str(row["id"]) for row in self.rows(response)})
        self.assertFalse(can_manage_shopping_access(self.teen, legacy))
        self.assertTrue(can_manage_shopping_access(self.owner, legacy))

    def test_private_list_is_only_visible_to_creator(self):
        response = self.client.post("/api/shopping-lists/", {
            "family": str(self.family.id), "name": "Surprise", "visibility": "private",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        list_id = response.data["id"]
        item = ShoppingItem.objects.create(shopping_list_id=list_id, name="Secret", added_by=self.owner)

        teen_client = APIClient(); teen_client.force_authenticate(self.teen)
        self.assertNotIn(list_id, {str(row["id"]) for row in self.rows(teen_client.get("/api/shopping-lists/"))})
        self.assertEqual(teen_client.get(f"/api/shopping-items/{item.id}/").status_code, 404)
        self.assertEqual(teen_client.post(f"/api/smart/shopping/{item.id}/favorite/", {}, format="json").status_code, 404)
        self.assertEqual(teen_client.post(f"/api/smart/shopping-lists/{list_id}/clear-checked/", {}, format="json").status_code, 404)

    def test_selected_visibility_and_responsibility_are_separate(self):
        response = self.client.post("/api/shopping-lists/", {
            "family": str(self.family.id),
            "name": "Teen list",
            "visibility": "selected",
            "visible_members": [str(self.teen_member.id)],
            "responsible_members": [str(self.adult_member.id)],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        list_id = response.data["id"]

        teen_client = APIClient(); teen_client.force_authenticate(self.teen)
        self.assertIn(list_id, {str(row["id"]) for row in self.rows(teen_client.get("/api/shopping-lists/"))})

        adult_client = APIClient(); adult_client.force_authenticate(self.other_adult)
        self.assertNotIn(list_id, {str(row["id"]) for row in self.rows(adult_client.get("/api/shopping-lists/"))})
        self.assertEqual(adult_client.post("/api/shopping-items/", {"shopping_list": list_id, "name": "No access"}, format="json").status_code, 403)

    def test_cross_family_audience_ids_are_rejected(self):
        response = self.client.post("/api/shopping-lists/", {
            "family": str(self.family.id),
            "name": "Invalid",
            "visibility": "selected",
            "visible_members": [str(self.outside_member.id)],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ShoppingList.objects.filter(family=self.family, name="Invalid").exists())

    def test_access_list_cannot_move_between_families(self):
        Membership.objects.create(family=self.other_family, user=self.owner, role=Membership.Role.ADULT, display_name="Owner elsewhere")
        response = self.client.post("/api/shopping-lists/", {
            "family": str(self.family.id), "name": "Anchored", "visibility": "private",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        list_id = response.data["id"]
        moved = self.client.patch(f"/api/shopping-lists/{list_id}/", {"family": str(self.other_family.id)}, format="json")
        self.assertEqual(moved.status_code, 400)
        shopping = ShoppingList.objects.get(id=list_id)
        self.assertEqual(shopping.family_id, self.family.id)

    def test_restricting_family_list_scrubs_shared_learning(self):
        shopping = ShoppingList.objects.create(family=self.family, name="Was a family list")
        item = ShoppingItem.objects.create(shopping_list=shopping, name="Secret tea", quantity="2", added_by=self.owner)
        EntryMemory.objects.create(
            family=self.family,
            kind=EntryMemory.Kind.SHOPPING,
            normalized_name="secret tea",
            name="Secret tea",
            data={"quantity": "2"},
            use_count=3,
            last_used_at=timezone.now(),
        )
        ShoppingPurchaseEvent.objects.create(
            family=self.family,
            shopping_list=shopping,
            source_item_id=item.id,
            normalized_name="secret tea",
            display_name="Secret tea",
            quantity="2",
            purchased_at=timezone.now(),
            purchased_by=self.owner,
        )
        response = self.client.patch(f"/api/shopping-lists/{shopping.id}/", {"visibility": "private"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(EntryMemory.objects.filter(family=self.family, kind=EntryMemory.Kind.SHOPPING, normalized_name="secret tea").exists())
        self.assertFalse(ShoppingPurchaseEvent.objects.filter(shopping_list=shopping).exists())

    def test_private_access_does_not_enter_family_notification_targets(self):
        response = self.client.post("/api/shopping-lists/", {
            "family": str(self.family.id), "name": "Private", "visibility": "private",
        }, format="json")
        shopping = ShoppingList.objects.get(id=response.data["id"])
        self.assertEqual(set(shopping_notification_user_ids(shopping)), {self.owner.id})

    def test_context_registry_hides_private_list_and_items(self):
        response = self.client.post("/api/shopping-lists/", {
            "family": str(self.family.id), "name": "Private", "visibility": "private",
        }, format="json")
        shopping = ShoppingList.objects.get(id=response.data["id"])
        item = ShoppingItem.objects.create(shopping_list=shopping, name="Secret", added_by=self.owner)
        registry = default_context_registry()
        owner_refs = registry.resolve_many(self.owner, self.family, [ContextRef("shopping_list", shopping.id), ContextRef("shopping_item", item.id)])
        teen_refs = registry.resolve_many(self.teen, self.family, [ContextRef("shopping_list", shopping.id), ContextRef("shopping_item", item.id)])
        self.assertEqual(len(owner_refs), 2)
        self.assertEqual(teen_refs, {})

    def test_dashboard_excludes_hidden_lists(self):
        public = ShoppingList.objects.create(family=self.family, name="Public")
        private = ShoppingList.objects.create(family=self.family, name="Private")
        ShoppingListAccess.objects.create(shopping_list=private, created_by=self.owner, visibility=ShoppingListAccess.Visibility.PRIVATE)
        teen_client = APIClient(); teen_client.force_authenticate(self.teen)
        response = teen_client.get(f"/api/dashboard/?family={self.family.id}")
        self.assertEqual(response.status_code, 200)
        ids = {str(row["id"]) for row in response.data["shopping_lists"]}
        self.assertIn(str(public.id), ids)
        self.assertNotIn(str(private.id), ids)

    def test_hidden_list_cannot_be_targeted_by_template_or_store_assignment(self):
        private = ShoppingList.objects.create(family=self.family, name="Private")
        ShoppingListAccess.objects.create(shopping_list=private, created_by=self.owner, visibility=ShoppingListAccess.Visibility.PRIVATE)
        teen_client = APIClient(); teen_client.force_authenticate(self.teen)
        store_response = teen_client.post("/api/shopping-stores/", {"family": str(self.family.id), "name": "Store"}, format="json")
        self.assertEqual(store_response.status_code, 201)
        assign = teen_client.post(f"/api/shopping-stores/{store_response.data['id']}/assign/", {"shopping_list": str(private.id)}, format="json")
        self.assertEqual(assign.status_code, 400)

    def test_prediction_accept_rejects_hidden_target_and_does_not_echo_hidden_item(self):
        private = ShoppingList.objects.create(family=self.family, name="Private")
        ShoppingListAccess.objects.create(shopping_list=private, created_by=self.owner, visibility=ShoppingListAccess.Visibility.PRIVATE)
        secret = ShoppingItem.objects.create(shopping_list=private, name="Secret milk", added_by=self.owner)
        public = ShoppingList.objects.create(family=self.family, name="Public")
        teen_client = APIClient(); teen_client.force_authenticate(self.teen)

        hidden_target = teen_client.post("/api/shopping-predictions/accept/", {
            "family": str(self.family.id), "key": "anything", "list": str(private.id),
        }, format="json")
        self.assertEqual(hidden_target.status_code, 403)

        guessed_key = teen_client.post("/api/shopping-predictions/accept/", {
            "family": str(self.family.id), "key": "secret milk", "list": str(public.id),
        }, format="json")
        self.assertEqual(guessed_key.status_code, 400)
        self.assertNotIn(str(secret.id), str(guessed_key.data))

    def test_prediction_accept_without_visible_list_creates_safe_family_target(self):
        private = ShoppingList.objects.create(family=self.family, name="Owner private")
        ShoppingListAccess.objects.create(shopping_list=private, created_by=self.owner, visibility=ShoppingListAccess.Visibility.PRIVATE)
        ShoppingItem.objects.create(shopping_list=private, name="Milk", added_by=self.owner)
        now = timezone.now()
        for days_ago in (28, 21, 14):
            ShoppingPurchaseEvent.objects.create(
                family=self.family,
                normalized_name="milk",
                display_name="Milk",
                purchased_at=now - timedelta(days=days_ago),
            )
        teen_client = APIClient(); teen_client.force_authenticate(self.teen)

        predictions = teen_client.get(f"/api/shopping-predictions/?family={self.family.id}")
        self.assertEqual(predictions.status_code, 200)
        self.assertIn("milk", {row["key"] for row in predictions.data["suggestions"]})
        accepted = teen_client.post("/api/shopping-predictions/accept/", {
            "family": str(self.family.id), "key": "milk",
        }, format="json")
        self.assertEqual(accepted.status_code, 201)
        self.assertNotEqual(str(accepted.data["item"]["shopping_list"]), str(private.id))
        visible_ids = {str(row["id"]) for row in self.rows(teen_client.get("/api/shopping-lists/"))}
        self.assertIn(str(accepted.data["item"]["shopping_list"]), visible_ids)
        self.assertNotIn(str(private.id), visible_ids)
