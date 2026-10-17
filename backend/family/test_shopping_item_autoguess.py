from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList
from .shopping_autoguess_models import ShoppingItemCreateReceipt


class ShoppingItemAutoguessQuickAddTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="autoguess-owner", password="x")
        self.outsider = User.objects.create_user(username="autoguess-outsider", password="x")
        self.family = Family.objects.create(name="Autoguess Family", slug="autoguess-family")
        self.other_family = Family.objects.create(name="Other Autoguess Family", slug="other-autoguess-family")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER)
        self.shopping_list = ShoppingList.objects.create(family=self.family, name="Food")
        self.other_list = ShoppingList.objects.create(family=self.family, name="Drugstore")
        self.foreign_list = ShoppingList.objects.create(family=self.other_family, name="Foreign")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _add(self, **overrides):
        payload = {
            "family": str(self.family.id),
            "shopping_list": str(self.shopping_list.id),
            "name": "Milk",
            **overrides,
        }
        return self.client.post("/api/smart/shopping/quick-add/", payload, format="json")

    def test_same_mutation_retry_returns_exactly_one_canonical_item(self):
        mutation = "82f31f8a-cdc7-461d-b01a-4ce65486aaad"
        first = self._add(client_mutation_id=mutation, quantity="2")
        second = self._add(client_mutation_id=mutation, quantity="9")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data["reused"])
        self.assertEqual(first.data["item"]["id"], second.data["item"]["id"])
        self.assertEqual(second.data["item"]["quantity"], "2")
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.shopping_list).count(), 1)
        self.assertEqual(ShoppingItemCreateReceipt.objects.filter(shopping_list=self.shopping_list).count(), 1)

    def test_same_name_with_different_mutations_never_silently_merges(self):
        first = self._add(client_mutation_id="c893e15c-7dd3-4aa7-bfe0-c2e16d32d7a6")
        second = self._add(name="milk", client_mutation_id="56894258-f538-4479-b082-f755ab11def2")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertFalse(second.data["reused"])
        self.assertNotEqual(first.data["item"]["id"], second.data["item"]["id"])
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.shopping_list).count(), 2)

    def test_legacy_create_without_mutation_id_stays_compatible_and_explicit(self):
        first = self._add()
        second = self._add()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.shopping_list).count(), 2)
        self.assertEqual(ShoppingItemCreateReceipt.objects.count(), 0)

    def test_mutation_id_is_scoped_to_target_list(self):
        mutation = "f32751dd-f085-4c16-99da-5b5a9ad76828"
        first = self._add(client_mutation_id=mutation)
        second = self._add(shopping_list=str(self.other_list.id), client_mutation_id=mutation)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(ShoppingItemCreateReceipt.objects.filter(mutation_id=mutation).count(), 2)

    def test_foreign_list_cannot_be_targeted_with_a_known_mutation_id(self):
        response = self._add(
            shopping_list=str(self.foreign_list.id),
            client_mutation_id="5a4a9d31-e3a3-4d7e-9afc-5947ddcd8d25",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.foreign_list).count(), 0)
        self.assertEqual(ShoppingItemCreateReceipt.objects.count(), 0)

    def test_invalid_mutation_and_overlong_name_are_rejected(self):
        invalid_mutation = self._add(client_mutation_id="not-a-uuid")
        self.assertEqual(invalid_mutation.status_code, 400)

        invalid_name = self._add(name="x" * 161, client_mutation_id="78e9b62d-10b0-4db5-86a8-cb9fd9162761")
        self.assertEqual(invalid_name.status_code, 400)
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.shopping_list).count(), 0)
