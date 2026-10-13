import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from auth_identity.service import create_primary_identity
from family.models import Family, InboxItem, Membership
from .models import Conversation


class NativeFamilyMessengerTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Musterfamilie", slug="messenger-native-family")
        self.owner = self.user("owner", Membership.Role.OWNER, verified=True)
        self.adult = self.user("adult", Membership.Role.ADULT, verified=False)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def user(self, name, role, *, verified):
        user = get_user_model().objects.create_user(username=name, email=f"{name}@example.com", password="unique-password-42")
        if verified:
            create_primary_identity(user, user.email, verified=True)
        Membership.objects.create(user=user, family=self.family, role=role, display_name=name.title())
        return user

    def test_family_member_without_verified_email_is_visible_and_directly_chat_capable(self):
        contacts = self.client.get("/api/chat/family-contacts/")
        self.assertEqual(contacts.status_code, 200)
        self.assertEqual([row["user"]["id"] for row in contacts.data["results"]], [self.adult.pk])

        opened = self.client.post("/api/chat/family-conversations/", {"user_id": self.adult.pk}, format="json")
        self.assertEqual(opened.status_code, 201, opened.data)
        self.assertEqual(opened.data["channel"], "custom")

    def test_family_and_system_channels_are_canonical_and_system_is_read_only(self):
        first = self.client.get("/api/chat/conversations/")
        self.assertEqual(first.status_code, 200, first.data)
        channels = {row["channel"]: row for row in first.data["results"] if row.get("family_id") == str(self.family.pk)}
        self.assertEqual(set(channels), {"family", "system"})
        self.assertEqual(channels["family"]["title"], "Musterfamilie")
        self.assertEqual(channels["system"]["title"], "System")
        self.assertTrue(channels["family"]["can_send"])
        self.assertFalse(channels["system"]["can_send"])

        second = self.client.get("/api/chat/conversations/")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Conversation.objects.filter(family=self.family, channel="family").count(), 1)
        self.assertEqual(Conversation.objects.filter(family=self.family, channel="system").count(), 1)

        family_sent = self.client.post(
            f'/api/chat/conversations/{channels["family"]["id"]}/messages/',
            {"client_id": str(uuid.uuid4()), "body": "Hallo Familie"},
            format="json",
        )
        self.assertEqual(family_sent.status_code, 201, family_sent.data)
        system_sent = self.client.post(
            f'/api/chat/conversations/{channels["system"]["id"]}/messages/',
            {"client_id": str(uuid.uuid4()), "body": "Nicht erlaubt"},
            format="json",
        )
        self.assertEqual(system_sent.status_code, 403)

    def test_legacy_system_item_is_mirrored_as_system_user_message(self):
        self.client.get("/api/chat/conversations/")
        with self.captureOnCommitCallbacks(execute=True):
            item = InboxItem.objects.create(
                family=self.family,
                title="Warnung",
                body="Fenster schließen",
                source="weather_warning",
                status="new",
            )
        system = Conversation.objects.get(family=self.family, channel="system")
        self.assertEqual(system.messages.filter(client_id=item.pk).count(), 1)

        detail = self.client.get(f"/api/chat/conversations/{system.pk}/messages/")
        self.assertEqual(detail.status_code, 200, detail.data)
        migrated = next(row for row in detail.data["results"] if row["client_id"] == str(item.pk))
        self.assertEqual(migrated["sender_name"], "System")
        self.assertIn("Warnung", migrated["body"])
        self.assertIn("Fenster schließen", migrated["body"])
