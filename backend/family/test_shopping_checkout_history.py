from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .context_links import default_context_registry
from .models import Family, Membership, ShoppingItem, ShoppingList
from .shopping_models import ShoppingSession


class ShoppingCheckoutHistoryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="checkout-owner", password="x")
        self.partner = User.objects.create_user(username="checkout-partner", password="x")
        self.outsider = User.objects.create_user(username="checkout-outsider", password="x")
        self.family = Family.objects.create(name="Checkout Family", slug="checkout-family")
        self.other_family = Family.objects.create(name="Outside Family", slug="outside-checkout-family")
        self.owner_member = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        self.partner_member = Membership.objects.create(family=self.family, user=self.partner, role=Membership.Role.ADULT, display_name="Partner")
        Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER, display_name="Outsider")
        self.owner_client = APIClient(); self.owner_client.force_authenticate(self.owner)
        self.partner_client = APIClient(); self.partner_client.force_authenticate(self.partner)
        self.outsider_client = APIClient(); self.outsider_client.force_authenticate(self.outsider)
        created = self.owner_client.post("/api/shopping-lists/", {
            "family": str(self.family.id),
            "name": "Market",
            "store": "REWE",
            "visibility": "selected",
            "visible_members": [str(self.partner_member.id)],
        }, format="json")
        self.assertEqual(created.status_code, 201)
        self.list_id = created.data["id"]

    def test_completed_session_detail_and_history_preserve_item_privacy(self):
        started = self.owner_client.post("/api/shopping-sessions/start/", {"shopping_list": self.list_id}, format="json")
        self.assertEqual(started.status_code, 201)
        shopping_list = ShoppingList.objects.get(pk=self.list_id)
        ShoppingItem.objects.create(
            shopping_list=shopping_list,
            name="Milk",
            checked=True,
            checked_at=timezone.now(),
            added_by=self.owner,
        )
        ShoppingItem.objects.create(
            shopping_list=shopping_list,
            name="Surprise gift",
            checked=True,
            checked_at=timezone.now(),
            added_by=self.owner,
            hidden_from_user=self.partner,
        )

        completed = self.owner_client.post("/api/shopping-sessions/complete/", {
            "shopping_list": self.list_id,
            "session": started.data["session"]["id"],
            "open_items": "keep",
        }, format="json")
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.data["completion"]["purchased_count"], 2)
        session_id = completed.data["session"]["id"]

        partner_detail = self.partner_client.get(f"/api/shopping-sessions/{session_id}/")
        self.assertEqual(partner_detail.status_code, 200)
        self.assertEqual(partner_detail.data["completion"]["purchased_count"], 1)
        self.assertEqual([row["name"] for row in partner_detail.data["completion"]["purchased_items"]], ["Milk"])
        self.assertNotIn("hidden_from_user_id", partner_detail.data["completion"]["purchased_items"][0])

        partner_history = self.partner_client.get(f"/api/shopping-sessions/history/?shopping_list={self.list_id}")
        self.assertEqual(partner_history.status_code, 200)
        self.assertEqual(len(partner_history.data["results"]), 1)
        self.assertEqual(partner_history.data["results"][0]["completion"]["purchased_count"], 1)

        owner_detail = self.owner_client.get(f"/api/shopping-sessions/{session_id}/")
        self.assertEqual(owner_detail.status_code, 200)
        self.assertEqual(owner_detail.data["completion"]["purchased_count"], 2)

        outsider_detail = self.outsider_client.get(f"/api/shopping-sessions/{session_id}/")
        self.assertEqual(outsider_detail.status_code, 404)

    def test_completed_session_context_deep_link_reopens_exact_snapshot(self):
        session = ShoppingSession.objects.create(
            family=self.family,
            shopping_list=ShoppingList.objects.get(pk=self.list_id),
            status=ShoppingSession.Status.COMPLETED,
            started_by=self.owner,
            completed_by=self.owner,
            completed_at=timezone.now(),
            snapshot={"purchased_items": [], "open_items": [], "purchased_count": 0, "open_count": 0},
        )
        adapter = default_context_registry()._types["shopping_session"]
        self.assertEqual(
            adapter.deep_link(session),
            f"/?page=shopping&list={self.list_id}&mode=store&session={session.id}",
        )
