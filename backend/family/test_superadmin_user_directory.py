from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_identity.service import create_primary_identity
from auth_passkeys.models import WebAuthnCredential
from auth_sessions.models import AuthSession
from telemetry.models import AuditEvent, UsageEvent

from .models import Family, Membership


class SuperadminUserDirectoryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="directory-admin", password="pw")
        self.target = User.objects.create_user(username="directory-target", email="target@example.test", password="pw")
        self.inactive = User.objects.create_user(username="directory-inactive", email="inactive@example.test", password="pw", is_active=False)
        create_primary_identity(self.target, "target@example.test", verified=True)
        create_primary_identity(self.inactive, "inactive@example.test", verified=True)
        self.family = Family.objects.create(name="Directory Family", slug="directory-family")
        Membership.objects.create(family=self.family, user=self.target, role=Membership.Role.OWNER, display_name="Target Person")
        self.client = APIClient()

    def test_directory_exposes_aggregate_activity_and_auth_state_without_secrets(self):
        now = timezone.now()
        UsageEvent.objects.create(
            occurred_at=now - timedelta(minutes=5),
            bucket_start=now - timedelta(minutes=5),
            event_key="activity.foreground",
            user=self.target,
            family=self.family,
        )
        AuditEvent.objects.create(
            occurred_at=now - timedelta(minutes=10),
            event_key="auth.login.succeeded",
            actor=self.target,
            actor_class=AuditEvent.ActorClass.USER,
            outcome=AuditEvent.Outcome.SUCCESS,
            metadata={"auth_method": "password", "private": "must-not-leak"},
        )
        AuthSession.objects.create(
            user=self.target,
            auth_method=AuthSession.AuthMethod.PASSWORD,
            client_label="Private device label",
            last_seen_at=now,
            last_reauthenticated_at=now,
            absolute_expires_at=now + timedelta(hours=1),
            refresh_expires_at=now + timedelta(days=1),
            current_refresh_jti="private-current-jti",
            previous_refresh_jti="private-previous-jti",
        )
        AuthSession.objects.create(
            user=self.target,
            auth_method=AuthSession.AuthMethod.PASSWORD,
            client_label="Revoked device",
            last_seen_at=now,
            last_reauthenticated_at=now,
            absolute_expires_at=now + timedelta(hours=1),
            refresh_expires_at=now + timedelta(days=1),
            current_refresh_jti="revoked-private-jti",
            revoked_at=now,
        )
        WebAuthnCredential.objects.create(
            user=self.target,
            credential_id=b"private-credential-id",
            public_key=b"private-public-key",
            name="Private passkey name",
        )
        WebAuthnCredential.objects.create(
            user=self.target,
            credential_id=b"revoked-credential-id",
            public_key=b"revoked-public-key",
            name="Revoked passkey",
            revoked_at=now,
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/users/?q=directory-target&status=active&sort=-last_activity")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["sort"], "-last_activity")
        self.assertEqual(response.data["status"], "active")
        row = response.data["results"][0]
        self.assertEqual(row["id"], self.target.pk)
        self.assertEqual(row["family_count"], 1)
        self.assertEqual(row["active_sessions"], 1)
        self.assertTrue(row["auth_methods"]["password"])
        self.assertEqual(row["auth_methods"]["passkeys"], 1)
        self.assertIsNotNone(row["last_activity_at"])
        self.assertIsNotNone(row["last_login_at"])
        self.assertIsNotNone(row["created_at"])

        serialized = str(response.data)
        for secret in (
            "private-current-jti",
            "private-previous-jti",
            "private-credential-id",
            "private-public-key",
            "Private passkey name",
            "Private device label",
            "must-not-leak",
        ):
            self.assertNotIn(secret, serialized)

    def test_directory_status_filter_and_sort_are_server_side_and_allow_listed(self):
        self.client.force_authenticate(self.admin)

        inactive = self.client.get("/api/superadmin/users/?status=inactive&sort=-created_at")
        self.assertEqual(inactive.status_code, 200, inactive.data)
        self.assertEqual(inactive.data["count"], 1)
        self.assertEqual(inactive.data["results"][0]["id"], self.inactive.pk)

        bad_status = self.client.get("/api/superadmin/users/?status=suspended")
        self.assertEqual(bad_status.status_code, 400, bad_status.data)
        self.assertIn("active", bad_status.data["allowed_statuses"])

        bad_sort = self.client.get("/api/superadmin/users/?sort=password")
        self.assertEqual(bad_sort.status_code, 400, bad_sort.data)
        self.assertIn("username", bad_sort.data["allowed_sorts"])

    def test_expired_session_is_not_counted_as_active(self):
        now = timezone.now()
        AuthSession.objects.create(
            user=self.target,
            auth_method=AuthSession.AuthMethod.PASSWORD,
            last_seen_at=now - timedelta(days=2),
            last_reauthenticated_at=now - timedelta(days=2),
            absolute_expires_at=now - timedelta(hours=1),
            refresh_expires_at=now - timedelta(minutes=1),
            current_refresh_jti="expired-private-jti",
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/users/?q=directory-target")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"][0]["active_sessions"], 0)
        self.assertNotIn("expired-private-jti", str(response.data))
