from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, ShoppingList, TaskList
from .models_features import LoyaltyCard, NotificationPreference


class DomainNotificationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="notify-alice", password="test-pass-123")
        self.bob = User.objects.create_user(username="notify-bob", password="test-pass-123")
        self.outsider = User.objects.create_user(username="notify-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Notify Family", slug="notify-family")
        self.other = Family.objects.create(name="Other Notify Family", slug="other-notify-family")
        self.alice_member = Membership.objects.create(family=self.family, user=self.alice, role=Membership.Role.OWNER, display_name="Alice")
        self.bob_member = Membership.objects.create(family=self.family, user=self.bob, role=Membership.Role.ADULT, display_name="Bob")
        Membership.objects.create(family=self.other, user=self.outsider, role=Membership.Role.OWNER)
        self.tasks = TaskList.objects.create(family=self.family, name="Haushalt")
        self.shopping = ShoppingList.objects.create(family=self.family, name="REWE")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    @patch("family.domain_notifications.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_task_push_excludes_actor_and_stays_in_family(self, sender):
        response = self.client.post("/api/tasks/", {"family": str(self.family.id), "task_list": str(self.tasks.id), "title": "Müll rausbringen"}, format="json")
        self.assertEqual(response.status_code, 201)
        users = [call.args[0] for call in sender.call_args_list]
        self.assertIn(self.bob, users)
        self.assertNotIn(self.alice, users)
        self.assertNotIn(self.outsider, users)
        self.assertIn("task=", sender.call_args_list[-1].args[3])

    @patch("family.domain_notifications.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_disabled_task_preference_suppresses_push(self, sender):
        NotificationPreference.objects.create(membership=self.bob_member, tasks=False)
        response = self.client.post("/api/tasks/", {"family": str(self.family.id), "task_list": str(self.tasks.id), "title": "Leise Aufgabe"}, format="json")
        self.assertEqual(response.status_code, 201)
        sender.assert_not_called()

    @patch("family.domain_notifications.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_disabled_shopping_preference_suppresses_push(self, sender):
        NotificationPreference.objects.create(membership=self.bob_member, shopping=False)
        response = self.client.post("/api/shopping-items/", {"shopping_list": str(self.shopping.id), "name": "Milch"}, format="json")
        self.assertEqual(response.status_code, 201)
        sender.assert_not_called()

    @patch("family.domain_notifications.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_disabled_calendar_preference_suppresses_push(self, sender):
        NotificationPreference.objects.create(membership=self.bob_member, calendar=False)
        response = self.client.post("/api/events/", {"family": str(self.family.id), "type": "calendar.event", "title": "Elternabend"}, format="json")
        self.assertEqual(response.status_code, 201)
        sender.assert_not_called()

    @patch("family.domain_notifications.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_shopping_and_calendar_events_push(self, sender):
        response = self.client.post("/api/shopping-items/", {"shopping_list": str(self.shopping.id), "name": "Milch"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(any("shopping" in call.args[3] for call in sender.call_args_list))
        sender.reset_mock()
        response = self.client.post("/api/events/", {"family": str(self.family.id), "type": "calendar.event", "title": "Elternabend"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(any("calendar" in call.args[3] for call in sender.call_args_list))

    @patch("family.domain_notifications.send_user_push", return_value={"sent": 1, "errors": 0})
    def test_assignment_is_targeted(self, sender):
        response = self.client.post("/api/tasks/", {"family": str(self.family.id), "task_list": str(self.tasks.id), "title": "Elternabend vorbereiten", "assignee": self.bob.id}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(any(call.args[0] == self.bob and "assigned" in call.kwargs.get("tag", "") for call in sender.call_args_list))
        self.assertFalse(any(call.args[0] == self.outsider for call in sender.call_args_list))

    def test_preferences_are_per_family_membership(self):
        response = self.client.patch(f"/api/push/preferences/?family={self.family.id}", {"shopping": False, "task_assigned": False}, format="json")
        self.assertEqual(response.status_code, 200)
        pref = NotificationPreference.objects.get(membership=self.alice_member)
        self.assertFalse(pref.shopping)
        self.assertFalse(pref.task_assigned)


class LoyaltyCardTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="card-owner", password="test-pass-123")
        self.shared = User.objects.create_user(username="card-shared", password="test-pass-123")
        self.private = User.objects.create_user(username="card-private", password="test-pass-123")
        self.outsider = User.objects.create_user(username="card-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Wallet Family", slug="wallet-family")
        self.other = Family.objects.create(name="Wallet Other", slug="wallet-other")
        self.owner_member = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        self.shared_member = Membership.objects.create(family=self.family, user=self.shared, role=Membership.Role.ADULT)
        self.private_member = Membership.objects.create(family=self.family, user=self.private, role=Membership.Role.TEEN)
        Membership.objects.create(family=self.other, user=self.outsider, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def rows(self, response):
        data = response.data
        return data.get("results", data) if hasattr(data, "get") else data

    def test_manual_card_sharing_and_acl(self):
        response = self.client.post("/api/loyalty-cards/", {
            "family": str(self.family.id), "name": "PAYBACK", "color": "#003b7a",
            "holder_name": "Alice", "customer_number": "12345678",
            "barcode_value": "123456789012", "barcode_format": "code128",
            "shared_with_ids": [str(self.shared_member.id)],
        }, format="json")
        self.assertEqual(response.status_code, 201)
        card_id = response.data["id"]
        self.client.force_authenticate(self.shared)
        shared = self.client.get(f"/api/loyalty-cards/{card_id}/")
        self.assertEqual(shared.status_code, 200)
        self.assertEqual(shared.data["barcode_value"], "123456789012")
        denied_update = self.client.patch(f"/api/loyalty-cards/{card_id}/", {"note": "Nope"}, format="json")
        self.assertEqual(denied_update.status_code, 403)
        self.client.force_authenticate(self.private)
        self.assertEqual(self.client.get(f"/api/loyalty-cards/{card_id}/").status_code, 404)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/api/loyalty-cards/{card_id}/").status_code, 404)

    def test_revoked_share_disappears_from_sync(self):
        card = LoyaltyCard.objects.create(family=self.family, name="IKEA Family", barcode_value="ABC123", barcode_format="code128", created_by=self.owner)
        card.shared_with.add(self.shared_member)
        self.client.force_authenticate(self.shared)
        self.assertEqual(len(self.rows(self.client.get(f"/api/loyalty-cards/sync/?family={self.family.id}"))), 1)
        self.client.force_authenticate(self.owner)
        response = self.client.patch(f"/api/loyalty-cards/{card.id}/", {"shared_with_ids": []}, format="json")
        self.assertEqual(response.status_code, 200)
        self.client.force_authenticate(self.shared)
        self.assertEqual(len(self.rows(self.client.get(f"/api/loyalty-cards/sync/?family={self.family.id}"))), 0)

    def test_creator_loses_access_after_leaving_family(self):
        card = LoyaltyCard.objects.create(family=self.family, name="Former member card", barcode_value="ABC123", barcode_format="code128", created_by=self.owner)
        self.owner_member.delete()
        response = self.client.get(f"/api/loyalty-cards/{card.id}/")
        self.assertEqual(response.status_code, 404)
        sync = self.client.get(f"/api/loyalty-cards/sync/?family={self.family.id}")
        self.assertEqual(len(self.rows(sync)), 0)

    def test_barcode_format_validation(self):
        response = self.client.post("/api/loyalty-cards/", {
            "family": str(self.family.id), "name": "EAN", "barcode_value": "123", "barcode_format": "ean13",
        }, format="json")
        self.assertEqual(response.status_code, 400)
