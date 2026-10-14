from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList, UserProfile
from .shopping_models import ShoppingSession


class ShoppingStoreRegressionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="store-owner", password="x")
        self.partner = User.objects.create_user(username="store-partner", password="x")
        self.family = Family.objects.create(name="Store Family", slug="store-family")
        self.owner_member = Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.partner_member = Membership.objects.create(
            family=self.family,
            user=self.partner,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_shopping_audience_options_expose_canonical_avatar_appearance(self):
        UserProfile.objects.create(
            user=self.partner,
            avatar_mode="icon",
            avatar_icon_key="rocket",
            avatar_color="#2563EB",
        )

        response = self.client.get(f"/api/shopping-audience-options/?family={self.family.id}")

        self.assertEqual(response.status_code, 200)
        partner = next(row for row in response.data["members"] if row["user_id"] == self.partner.id)
        self.assertEqual(partner["display_name"], "Sam")
        self.assertEqual(partner["avatar_mode"], "icon")
        self.assertEqual(partner["avatar_icon_key"], "rocket")
        self.assertEqual(partner["avatar_color"], "#2563EB")
        self.assertEqual(partner["avatar_url"], "")

    def test_checkout_persists_snapshot_before_deleting_purchased_items(self):
        shopping_list = ShoppingList.objects.create(family=self.family, name="Drogerie")
        started = self.client.post(
            "/api/shopping-sessions/start/",
            {"shopping_list": str(shopping_list.id)},
            format="json",
        )
        self.assertEqual(started.status_code, 201)
        session_id = started.data["session"]["id"]
        items = [
            ShoppingItem.objects.create(shopping_list=shopping_list, name="Seife", checked=True, added_by=self.owner),
            ShoppingItem.objects.create(shopping_list=shopping_list, name="Zahnpasta", checked=True, added_by=self.owner),
        ]
        observed = []

        def observe_checkout(sender, instance, **kwargs):
            if instance.shopping_list_id != shopping_list.id:
                return
            session = ShoppingSession.objects.get(id=session_id)
            observed.append((session.status, session.snapshot.get("purchased_count")))

        post_delete.connect(observe_checkout, sender=ShoppingItem, dispatch_uid="shopping-checkout-snapshot-regression")
        try:
            response = self.client.post(
                "/api/shopping-sessions/complete/",
                {"shopping_list": str(shopping_list.id), "session": session_id, "open_items": "keep"},
                format="json",
            )
        finally:
            post_delete.disconnect(sender=ShoppingItem, dispatch_uid="shopping-checkout-snapshot-regression")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["completion"]["purchased_count"], 2)
        self.assertEqual(response.data["completion"]["open_count"], 0)
        self.assertEqual(observed, [(ShoppingSession.Status.COMPLETED, 2), (ShoppingSession.Status.COMPLETED, 2)])
        self.assertFalse(ShoppingItem.objects.filter(id__in=[item.id for item in items]).exists())
