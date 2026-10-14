from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingItem, ShoppingList
from .shopping_models import ShoppingSession


class ShoppingCheckoutCleanupTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="checkout-cleanup", password="x")
        self.family = Family.objects.create(name="Checkout Family", slug="checkout-cleanup-family")
        Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.shopping_list = ShoppingList.objects.create(family=self.family, name="Drogerie")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_completed_session_survives_cleanup_failure_and_retry_finishes_cleanup(self):
        item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list,
            name="Shampoo",
            checked=True,
            checked_at=timezone.now(),
            added_by=self.user,
        )
        session = ShoppingSession.objects.create(
            family=self.family,
            shopping_list=self.shopping_list,
            started_by=self.user,
            started_at=timezone.now(),
            last_activity_at=timezone.now(),
        )
        payload = {
            "shopping_list": str(self.shopping_list.id),
            "session": str(session.id),
            "open_items": "keep",
        }

        with patch(
            "family.shopping_session_views._cleanup_completed_session_items",
            side_effect=RuntimeError("simulated cleanup failure"),
        ):
            completed = self.client.post("/api/shopping-sessions/complete/", payload, format="json")

        self.assertEqual(completed.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.status, ShoppingSession.Status.COMPLETED)
        self.assertEqual(session.snapshot["purchased_count"], 1)
        self.assertEqual(session.snapshot["purchased_items"][0]["name"], "Shampoo")
        self.assertTrue(ShoppingItem.objects.filter(id=item.id).exists())
        original_snapshot = session.snapshot

        retried = self.client.post("/api/shopping-sessions/complete/", payload, format="json")
        self.assertEqual(retried.status_code, 200)
        self.assertFalse(ShoppingItem.objects.filter(id=item.id).exists())
        session.refresh_from_db()
        self.assertEqual(session.snapshot, original_snapshot)
        self.assertEqual(retried.data["completion"]["purchased_count"], 1)
