from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from telemetry.models import AuditEvent

from .service import create_primary_identity, verification_token


class EmailVerificationTelemetryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="verification-telemetry-user",
            email="verify@example.test",
            password="test-pass-123",
        )
        self.client = APIClient()

    def test_successful_verification_emits_one_privacy_bounded_audit_event(self):
        identity = create_primary_identity(self.user, "verify@example.test")
        token = verification_token(identity)

        first = self.client.post("/api/auth/email/verify/", {"token": token}, format="json")
        second = self.client.post("/api/auth/email/verify/", {"token": token}, format="json")

        self.assertEqual(first.status_code, 200, first.data)
        self.assertTrue(first.data["changed"])
        self.assertEqual(second.status_code, 200, second.data)
        self.assertFalse(second.data["changed"])

        events = AuditEvent.objects.filter(event_key="auth.email.verified", actor=self.user)
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.actor_class, AuditEvent.ActorClass.USER)
        self.assertEqual(event.outcome, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(event.reason, "user_request")
        self.assertEqual(event.target_type, "user")
        self.assertEqual(event.target_id, str(self.user.pk))
        self.assertEqual(event.metadata, {})
        self.assertEqual(event.request_id, "")
        self.assertIsNone(event.family_id)

    def test_invalid_verification_token_emits_no_audit_event(self):
        response = self.client.post(
            "/api/auth/email/verify/",
            {"token": "not-a-valid-verification-token"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(AuditEvent.objects.filter(event_key="auth.email.verified").exists())
