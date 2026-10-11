from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_identity.models import EmailIdentity
from auth_passkeys.models import WebAuthnCredential
from auth_sessions.models import AuthSession
from telemetry.models import AuditEvent

from .models import Family, FamilyInvitation, InboxItem, Membership


class SuperadminUserDetailTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="user-detail-admin", password="pw")
        self.target = User.objects.create_user(
            username="user-detail-target",
            email="target@example.test",
            password="pw",
        )
        self.other = User.objects.create_user(username="user-detail-other", password="pw")
        self.family = Family.objects.create(name="User Detail Family", slug="user-detail-family")
        Membership.objects.create(
            family=self.family,
            user=self.target,
            role=Membership.Role.ADULT,
            display_name="Target Person",
        )
        Membership.objects.create(
            family=self.family,
            user=self.other,
            role=Membership.Role.OWNER,
            display_name="Other Person",
        )
        EmailIdentity.objects.create(
            user=self.target,
            kind=EmailIdentity.Kind.PRIMARY,
            email="target@example.test",
            email_normalized="target@example.test",
            verified_at=timezone.now(),
        )
        self.client = APIClient()

    def test_normal_user_cannot_read_user_detail(self):
        self.client.force_authenticate(self.other)
        response = self.client.get(f"/api/superadmin/users/{self.target.pk}/")
        self.assertEqual(response.status_code, 403)

    def test_unknown_user_returns_404(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/users/999999/")
        self.assertEqual(response.status_code, 404)

    def test_detail_returns_bounded_security_metadata_without_secrets_or_family_content(self):
        now = timezone.now()
        active_session = AuthSession.objects.create(
            user=self.target,
            auth_method=AuthSession.AuthMethod.PASSKEY,
            client_label="Desktop browser",
            last_seen_at=now - timedelta(minutes=5),
            last_reauthenticated_at=now - timedelta(minutes=10),
            absolute_expires_at=now + timedelta(days=5),
            refresh_expires_at=now + timedelta(days=2),
            current_refresh_jti="private-current-refresh-jti",
            previous_refresh_jti="private-previous-refresh-jti",
        )
        AuthSession.objects.create(
            user=self.target,
            auth_method=AuthSession.AuthMethod.PASSWORD,
            client_label="Old browser",
            last_seen_at=now - timedelta(days=2),
            last_reauthenticated_at=now - timedelta(days=2),
            absolute_expires_at=now + timedelta(days=1),
            refresh_expires_at=now + timedelta(hours=12),
            current_refresh_jti="private-revoked-refresh-jti",
            revoked_at=now - timedelta(days=1),
            revoked_reason="user_request",
        )
        WebAuthnCredential.objects.create(
            user=self.target,
            credential_id=b"private-active-credential-id",
            public_key=b"private-active-public-key",
            name="Private passkey label",
            last_used_at=now - timedelta(hours=1),
        )
        WebAuthnCredential.objects.create(
            user=self.target,
            credential_id=b"private-revoked-credential-id",
            public_key=b"private-revoked-public-key",
            name="Private revoked passkey label",
            revoked_at=now - timedelta(days=1),
        )

        pending_invite = FamilyInvitation.objects.create(
            family=self.family,
            invited_by=self.other,
            role=Membership.Role.ADULT,
            email="target@example.test",
            display_name="Target pending invite",
            expires_at=now + timedelta(days=3),
            token="private-pending-invite-token",
        )
        accepted_invite = FamilyInvitation.objects.create(
            family=self.family,
            invited_by=self.other,
            role=Membership.Role.ADULT,
            email="old-target@example.test",
            display_name="Target accepted invite",
            expires_at=now + timedelta(days=1),
            accepted_at=now - timedelta(days=1),
            accepted_by=self.target,
            token="private-accepted-invite-token",
        )

        AuditEvent.objects.create(
            occurred_at=now - timedelta(minutes=2),
            event_key="auth.login.succeeded",
            actor=self.target,
            actor_class=AuditEvent.ActorClass.USER,
            family=self.family,
            outcome=AuditEvent.Outcome.SUCCESS,
            reason="authenticated",
            request_id="private-auth-request-id",
            target_type="session",
            target_id="private-session-target-id",
            metadata={
                "auth_method": "passkey",
                "ip": "203.0.113.42",
                "credential_id": "private-audit-credential-id",
                "secret": "raw-audit-secret",
            },
        )
        AuditEvent.objects.create(
            occurred_at=now - timedelta(minutes=3),
            event_key="auth.login.failed",
            actor=self.target,
            actor_class=AuditEvent.ActorClass.USER,
            family=self.family,
            outcome=AuditEvent.Outcome.FAILED,
            reason="invalid_credentials",
            request_id="private-failed-request-id",
            metadata={"auth_method": "not-allow-listed", "identifier": "private-login-identifier"},
        )
        InboxItem.objects.create(
            family=self.family,
            title="PRIVATE FAMILY TITLE MUST NOT LEAK",
            body="PRIVATE FAMILY BODY MUST NOT LEAK",
            created_by=self.target,
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get(f"/api/superadmin/users/{self.target.pk}/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"]["id"], self.target.pk)
        self.assertEqual(response.data["user"]["memberships"][0]["family_id"], str(self.family.pk))
        self.assertEqual(response.data["security"]["passkeys"]["active"], 1)
        self.assertEqual(response.data["security"]["passkeys"]["revoked"], 1)
        self.assertEqual(response.data["security"]["sessions"]["active"], 1)
        self.assertEqual(response.data["security"]["sessions"]["results"][0]["auth_method"], "passkey")
        self.assertEqual(response.data["security"]["last_successful_auth_method"], "passkey")

        invite_states = {row["state"] for row in response.data["invitations"]["results"]}
        self.assertEqual(invite_states, {"pending", "accepted"})
        timeline = response.data["auth_timeline"]["results"]
        self.assertEqual(timeline[0]["event_key"], "auth.login.succeeded")
        self.assertEqual(timeline[0]["auth_method"], "passkey")
        self.assertIsNone(timeline[1]["auth_method"])

        serialized = str(response.data)
        for secret in (
            active_session.current_refresh_jti,
            active_session.previous_refresh_jti,
            pending_invite.token,
            accepted_invite.token,
            "private-pending-invite-token",
            "private-accepted-invite-token",
            "private-active-credential-id",
            "private-active-public-key",
            "private-revoked-credential-id",
            "private-revoked-public-key",
            "Private passkey label",
            "Private revoked passkey label",
            "private-auth-request-id",
            "private-failed-request-id",
            "private-session-target-id",
            "private-audit-credential-id",
            "raw-audit-secret",
            "private-login-identifier",
            "203.0.113.42",
            "PRIVATE FAMILY TITLE MUST NOT LEAK",
            "PRIVATE FAMILY BODY MUST NOT LEAK",
        ):
            self.assertNotIn(secret, serialized)

        for forbidden_key in (
            "current_refresh_jti",
            "previous_refresh_jti",
            "credential_id",
            "public_key",
            "request_id",
            "metadata",
        ):
            self.assertNotIn(forbidden_key, serialized)
