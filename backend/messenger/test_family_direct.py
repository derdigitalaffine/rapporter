import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from auth_identity.service import create_primary_identity
from family.models import Family, Membership
from .models import Friendship


class FamilyDirectMessengerTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Shared", slug="messenger-family-direct")
        self.one = self.user("one", "adult")
        self.two = self.user("two", "owner")
        self.child = self.user("child", "child")
        self.client = APIClient()
        self.client.force_authenticate(self.one)

    def user(self, name, role):
        user = get_user_model().objects.create_user(username=name, email=f"{name}@example.com", password="unique-password-42")
        create_primary_identity(user, user.email, verified=True)
        Membership.objects.create(user=user, family=self.family, role=role, display_name=name.title())
        return user

    def test_family_members_chat_without_invitation_and_access_expires_with_membership(self):
        contacts = self.client.get("/api/chat/family-contacts/")
        self.assertEqual(contacts.status_code, 200)
        self.assertEqual([row["user"]["id"] for row in contacts.data["results"]], [self.two.pk])
        self.assertEqual(contacts.data["derived_friendship_ids"], [])

        opened = self.client.post("/api/chat/family-conversations/", {"user_id": self.two.pk}, format="json")
        self.assertEqual(opened.status_code, 201, opened.data)
        conversation_id = opened.data["id"]
        friend = Friendship.objects.get(low_user_id=min(self.one.pk, self.two.pk), high_user_id=max(self.one.pk, self.two.pk))
        self.assertTrue(friend.family_derived)

        message = self.client.post(
            f"/api/chat/conversations/{conversation_id}/messages/",
            {"client_id": str(uuid.uuid4()), "body": "Direkter Familienchat"},
            format="json",
        )
        self.assertEqual(message.status_code, 201, message.data)

        contacts = self.client.get("/api/chat/family-contacts/")
        self.assertIn(str(friend.pk), contacts.data["derived_friendship_ids"])
        self.assertEqual(
            self.client.post("/api/chat/conversations/", {"kind": "group", "title": "No implicit consent", "friends": [str(friend.pk)]}, format="json").status_code,
            404,
        )

        Membership.objects.filter(user=self.two, family=self.family).delete()
        denied = self.client.post(
            f"/api/chat/conversations/{conversation_id}/messages/",
            {"client_id": str(uuid.uuid4()), "body": "Nicht mehr erlaubt"},
            format="json",
        )
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(self.client.get(f"/api/chat/conversations/{conversation_id}/messages/").status_code, 200)
        self.assertEqual(self.client.get("/api/chat/family-contacts/").data["results"], [])

    def test_children_are_not_exposed_as_direct_family_contacts(self):
        contacts = self.client.get("/api/chat/family-contacts/")
        ids = {row["user"]["id"] for row in contacts.data["results"]}
        self.assertNotIn(self.child.pk, ids)
        self.assertEqual(self.client.post("/api/chat/family-conversations/", {"user_id": self.child.pk}, format="json").status_code, 404)
