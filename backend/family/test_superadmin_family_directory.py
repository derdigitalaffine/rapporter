from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_identity.service import create_primary_identity
from entitlements.models import EntitlementGrant
from telemetry.models import UsageEvent

from .models import Family, Membership


class SuperadminFamilyDirectoryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="family-directory-admin", password="pw")
        self.owner = User.objects.create_user(username="family-directory-owner", email="owner@example.test", password="pw")
        create_primary_identity(self.owner, "owner@example.test", verified=True)
        self.family = Family.objects.create(name="Directory Family", slug="directory-family")
        Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Verified Owner",
        )
        self.client = APIClient()

    def test_directory_adds_activity_owner_and_entitlement_aggregates_without_grant_secrets(self):
        now = timezone.now()
        UsageEvent.objects.create(
            occurred_at=now - timedelta(minutes=5),
            bucket_start=now - timedelta(minutes=5),
            event_key="activity.foreground",
            user=self.owner,
            family=self.family,
        )
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.ADMIN_GRANT,
            plan_key="vip",
            active=True,
            source_ref="private-billing-reference",
            metadata={"private": "must-not-leak"},
            reason="private commercial reason",
            created_by=self.admin,
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/families/?q=Directory&status=active&sort=-last_activity")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 1)
        row = response.data[0]
        self.assertEqual(row["id"], str(self.family.id))
        self.assertEqual(row["member_count"], 1)
        self.assertEqual(row["owner_count"], 1)
        self.assertEqual(row["verified_owner_count"], 1)
        self.assertEqual(row["pending_invite_count"], 0)
        self.assertIsNotNone(row["last_activity_at"])
        self.assertEqual(row["owners"][0]["email"], "owner@example.test")
        self.assertTrue(row["owners"][0]["email_verified"])
        self.assertIn(row["entitlements"]["tier"], {"light", "premium", "vip"})
        self.assertIn("capabilities", row["entitlements"])
        self.assertIn("origin_summary", row["entitlements"])
        self.assertIn("origins", row["entitlements"])

        serialized = str(response.data)
        self.assertNotIn("private-billing-reference", serialized)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("private commercial reason", serialized)
        self.assertNotIn("source_ref", serialized)
        self.assertNotIn("metadata", serialized)

    def test_status_search_and_sort_are_allow_listed_without_changing_list_contract(self):
        suspended = Family.objects.create(
            name="Suspended Family",
            slug="suspended-family",
            status=Family.Status.SUSPENDED,
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/families/?status=suspended&sort=-created_at")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsInstance(response.data, list)
        self.assertEqual([row["id"] for row in response.data], [str(suspended.id)])

        bad_status = self.client.get("/api/superadmin/families/?status=archived")
        self.assertEqual(bad_status.status_code, 400, bad_status.data)
        self.assertIn("active", bad_status.data["allowed_statuses"])
        self.assertIn("suspended", bad_status.data["allowed_statuses"])

        bad_sort = self.client.get("/api/superadmin/families/?sort=metadata")
        self.assertEqual(bad_sort.status_code, 400, bad_sort.data)
        self.assertIn("name", bad_sort.data["allowed_sorts"])

    def test_unverified_owner_is_counted_but_not_marked_verified(self):
        User = get_user_model()
        other = User.objects.create_user(username="unverified-owner", email="unverified@example.test", password="pw")
        create_primary_identity(other, "unverified@example.test", verified=False)
        Membership.objects.create(
            family=self.family,
            user=other,
            role=Membership.Role.OWNER,
            display_name="Unverified Owner",
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/families/?q=directory-family")

        self.assertEqual(response.status_code, 200, response.data)
        row = response.data[0]
        self.assertEqual(row["owner_count"], 2)
        self.assertEqual(row["verified_owner_count"], 1)
        verification_by_username = {owner["username"]: owner["email_verified"] for owner in row["owners"]}
        self.assertTrue(verification_by_username["family-directory-owner"])
        self.assertFalse(verification_by_username["unverified-owner"])
