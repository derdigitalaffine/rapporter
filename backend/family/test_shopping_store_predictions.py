from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .memory import normalize_name
from .models import Family, Membership, ShoppingItem, ShoppingList, ShoppingPurchaseEvent
from .shopping_models import ShoppingListStoreProfile, ShoppingStore
from .shopping_purchase_context_models import ShoppingPurchaseStoreContext


class ShoppingStorePredictionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="store-prediction-owner", password="test-pass-123")
        self.family = Family.objects.create(name="Store Prediction Family", slug="store-prediction-family", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.shopping = ShoppingList.objects.create(family=self.family, name="Einkauf")
        self.store = ShoppingStore.objects.create(
            family=self.family,
            name="REWE",
            branch_label="West",
            address="Marktstraße 7",
            created_by=self.user,
        )
        ShoppingListStoreProfile.objects.create(shopping_list=self.shopping, store=self.store)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _purchase(self, days, quantity):
        event = ShoppingPurchaseEvent.objects.create(
            family=self.family,
            shopping_list=self.shopping,
            normalized_name=normalize_name("Milch"),
            display_name="Milch",
            quantity=quantity,
            category="Molkerei",
            aisle="Kühlung",
            store=self.store.display_label,
            purchased_at=timezone.now() - timedelta(days=days),
            purchased_by=self.user,
        )
        ShoppingPurchaseStoreContext.objects.create(
            purchase_event=event,
            shopping_store=self.store,
            address_snapshot=self.store.address,
        )

    def test_accept_uses_store_specific_learned_quantity(self):
        for days, quantity in ((16, "2 l"), (12, "2 l"), (8, "1 l"), (4, "2 l")):
            self._purchase(days, quantity)

        response = self.client.post(
            "/api/shopping-predictions/accept/",
            {
                "family": str(self.family.id),
                "list": str(self.shopping.id),
                "key": normalize_name("Milch"),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        item = ShoppingItem.objects.get(id=response.data["item"]["id"])
        self.assertEqual(item.shopping_list_id, self.shopping.id)
        self.assertEqual(item.quantity, "2 l")
        self.assertEqual(item.category, "Molkerei")
        self.assertEqual(item.aisle, "Kühlung")

    def test_purchase_signal_ignores_cross_family_store_assignment(self):
        other_family = Family.objects.create(name="Other Store Family", slug="other-store-family", timezone="Europe/Berlin")
        foreign_store = ShoppingStore.objects.create(
            family=other_family,
            name="Foreign Market",
            address="Fremdweg 1",
            created_by=self.user,
        )
        ShoppingListStoreProfile.objects.filter(shopping_list=self.shopping).update(store=foreign_store)
        item = ShoppingItem.objects.create(
            shopping_list=self.shopping,
            name="Brot",
            quantity="1",
            added_by=self.user,
        )

        response = self.client.patch(f"/api/shopping-items/{item.id}/", {"checked": True}, format="json")

        self.assertEqual(response.status_code, 200)
        event = ShoppingPurchaseEvent.objects.get(source_item_id=item.id)
        context = ShoppingPurchaseStoreContext.objects.get(purchase_event=event)
        self.assertEqual(event.store, "")
        self.assertIsNone(context.shopping_store_id)
        self.assertEqual(context.address_snapshot, "")
