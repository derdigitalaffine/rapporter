from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_identity.service import create_primary_identity
from telemetry.models import AuditEvent, UsageEvent

from .models import Family, FamilyInvitation, InboxItem, IntegrationSource, Membership


class SuperadminFamilyDetailTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="family-detail-admin", password="pw")
        self.owner = User.objects.create_user(username="family-detail-owner", email="owner@example.test", password="pw")
        self.adult = User.objects.create_user(username="family-detail-adult", email="adult@example.test", password="pw")
        create_primary_identity(self.owner, "owner@example.test", verified=True)
        create_primary_identity(self.adult, "adult@example.test", verified=False)
        self.family = Family.objects.create(name="Detail Family", slug="detail-family")
        Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Owner Person",
        )
        Membership.objects.create(
            family=self.family,
            user=self.adult,
            role=Membership.Role.ADULT,
            display_name="Adult Person",
        )
        self.client = APIClient()

    def test_normal_user_cannot_read_family_detail(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(f"/api/superadmin/families/{self.family.pk}/")
        self.assertEqual(response.status_code, 403)

    def test_detail_returns_operational_metadata_without_private_content_or_secrets(self):
        now = timezone.now()
        UsageEvent.objects.create(
            user=self.owner,
            family=self.family,
            event_key="activity.foreground",
            bucket_start=(now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0),
            occurred_at=now - timedelta(hours=1),
        )
        UsageEvent.objects.create(
            user=self.adult,
            family=self.family,
            event_key="activity.foreground",
            bucket_start=(now - timedelta(days=8)).replace(minute=0, second=0, microsecond=0),
            occurred_at=now - timedelta(days=8),
        )
        UsageEvent.objects.create(
            user=self.owner,
            family=self.family,
            event_key="module.used",
            dimension_key="documents",
            bucket_start=(now - timedelta(hours=2)).replace(minute=0, second=0, microsecond=0),
            occurred_at=now - timedelta(hours=2),
        )
        UsageEvent.objects.create(
            user=self.adult,
            family=self.family,
            event_key="module.used",
            dimension_key="tasks",
            bucket_start=(now - timedelta(days=2)).replace(minute=0, second=0, microsecond=0),
            occurred_at=now - timedelta(days=2),
        )

        integration = IntegrationSource.objects.create(
            family=self.family,
            name="Private integration label",
            kind=IntegrationSource.Kind.GENERIC,
            endpoint="https://private.integration.example.test/token-path",
            config={"token": "private-integration-token"},
            enabled=True,
            last_success_at=now - timedelta(hours=5),
            last_sync_status="failed",
            last_sync_error="private upstream error body",
            consecutive_failures=2,
        )
        self.assertIsNotNone(integration.pk)

        pending = FamilyInvitation.objects.create(
            family=self.family,
            invited_by=self.owner,
            role=Membership.Role.ADULT,
            email="invitee@example.test",
            display_name="Invitee",
            expires_at=now + timedelta(days=3),
        )
        FamilyInvitation.objects.create(
            family=self.family,
            invited_by=self.owner,
            role=Membership.Role.OWNER,
            email="expired-owner@example.test",
            display_name="Expired Owner",
            expires_at=now - timedelta(days=1),
        )

        InboxItem.objects.create(
            family=self.family,
            title="PRIVATE FAMILY TITLE MUST NOT LEAK",
            body="PRIVATE FAMILY BODY MUST NOT LEAK",
            created_by=self.owner,
        )
        AuditEvent.objects.create(
            occurred_at=now - timedelta(minutes=10),
            event_key="superadmin.family.suspended",
            actor=self.admin,
            actor_class=AuditEvent.ActorClass.SUPERADMIN,
            family=self.family,
            outcome=AuditEvent.Outcome.SUCCESS,
            reason="admin_action",
            request_id="private-request-id",
            target_type="family",
            target_id=str(self.family.pk),
            metadata={"private": "raw-audit-secret"},
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/superadmin/families/{self.family.pk}/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["family"]["id"], str(self.family.pk))
        self.assertEqual(len(response.data["memberships"]), 2)
        owner = next(row for row in response.data["memberships"] if row["role"] == Membership.Role.OWNER)
        self.assertTrue(owner["email_verified"])
        self.assertEqual(response.data["activity"]["active_users_7d"], 1)
        self.assertEqual(response.data["activity"]["active_users_30d"], 2)
        modules = {row["dimension_key"]: row["active_users"] for row in response.data["activity"]["module_adoption_30d"]}
        self.assertEqual(modules, {"documents": 1, "tasks": 1})
        self.assertEqual(response.data["integrations"]["enabled"], 1)
        self.assertEqual(response.data["integrations"]["degraded"], 1)
        invite_states = {row["email"]: row["state"] for row in response.data["invitations"]["results"]}
        self.assertEqual(invite_states["invitee@example.test"], "pending")
        self.assertEqual(invite_states["expired-owner@example.test"], "expired")
        self.assertEqual(response.data["superadmin_audit"]["results"][0]["event_key"], "superadmin.family.suspended")

        serialized = str(response.data)
        for secret in (
            pending.token,
            "private.integration.example.test",
            "private-integration-token",
            "private upstream error body",
            "PRIVATE FAMILY TITLE MUST NOT LEAK",
            "PRIVATE FAMILY BODY MUST NOT LEAK",
            "private-request-id",
            "raw-audit-secret",
        ):
            self.assertNotIn(secret, serialized)

    def test_patch_keeps_sensitive_action_reauthentication_guard(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/superadmin/families/{self.family.pk}/",
            {"status": Family.Status.SUSPENDED},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
