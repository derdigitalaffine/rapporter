from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AuditEvent


class SuperadminSecuritySummaryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="security-admin", password="pw")
        self.owner = User.objects.create_user(username="security-owner", password="pw")
        self.client = APIClient()

    def _event(self, event_key, *, occurred_at, outcome="success", metadata=None, reason=""):
        return AuditEvent.objects.create(
            event_key=event_key,
            occurred_at=occurred_at,
            actor=self.owner,
            actor_class=AuditEvent.ActorClass.USER,
            outcome=outcome,
            reason=reason,
            metadata=metadata or {},
        )

    def test_normal_user_cannot_read_security_summary(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/superadmin/security/summary/")
        self.assertEqual(response.status_code, 403)

    def test_invalid_period_is_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/security/summary/?period=13d")
        self.assertEqual(response.status_code, 400)
        self.assertIn("30d", response.data["allowed_periods"])

    def test_summary_aggregates_canonical_security_events_and_comparison(self):
        now = timezone.now()
        self._event(
            "auth.login.succeeded",
            occurred_at=now - timedelta(hours=1),
            metadata={"auth_method": "password"},
        )
        self._event(
            "auth.login.succeeded",
            occurred_at=now - timedelta(hours=2),
            metadata={"auth_method": "passkey"},
        )
        self._event(
            "auth.login.failed",
            occurred_at=now - timedelta(hours=3),
            outcome="failed",
            metadata={"auth_method": "password", "identifier_hash": "a" * 64},
            reason="invalid_credentials",
        )
        self._event(
            "auth.rate_limited",
            occurred_at=now - timedelta(hours=4),
            outcome="denied",
            metadata={"scope": "login", "identifier_hash": "b" * 64},
            reason="rate_limited",
        )
        self._event("auth.passkey.registered", occurred_at=now - timedelta(hours=5))
        self._event("auth.session.revoked", occurred_at=now - timedelta(hours=6))
        self._event(
            "auth.login.succeeded",
            occurred_at=now - timedelta(days=8),
            metadata={"auth_method": "password"},
        )
        self._event(
            "auth.login.failed",
            occurred_at=now - timedelta(days=9),
            outcome="failed",
            metadata={"auth_method": "password", "identifier_hash": "c" * 64},
            reason="invalid_credentials",
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/security/summary/?period=7d")

        self.assertEqual(response.status_code, 200)
        auth = response.data["authentication"]
        self.assertEqual(auth["login_success"]["value"], 2)
        self.assertEqual(auth["login_success"]["previous"], 1)
        self.assertEqual(auth["login_failure"]["value"], 1)
        self.assertEqual(auth["login_failure"]["previous"], 1)
        self.assertEqual(auth["login_success_rate_pct"], 66.7)
        self.assertEqual(auth["successful_login_methods"], {"password": 1, "passkey": 1, "legacy": 0})
        self.assertEqual(auth["passkey_share_pct"], 50.0)
        self.assertEqual(response.data["security_events"]["rate_limited"]["value"], 1)
        self.assertEqual(response.data["security_events"]["passkey_registered"]["value"], 1)
        self.assertEqual(response.data["security_events"]["session_revoked"]["value"], 1)

        serialized = str(response.data)
        self.assertNotIn("identifier_hash", serialized)
        self.assertNotIn("aaaaaaaa", serialized)
        self.assertNotIn("bbbbbbbb", serialized)

    def test_empty_window_does_not_invent_rates(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/security/summary/?period=24h")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["authentication"]["login_success_rate_pct"])
        self.assertIsNone(response.data["authentication"]["passkey_share_pct"])
