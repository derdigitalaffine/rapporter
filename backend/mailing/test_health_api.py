from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import TransactionalEmail
from .service import enqueue_transactional_email


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="FamilyOS <noreply@familyos.test>",
    APP_URL="https://familyos.test",
)
class SuperadminMailHealthApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="mail-admin",
            email="admin@example.com",
            password="admin-pass-123",
        )
        self.user = User.objects.create_user(
            username="mail-user",
            email="user@example.com",
            password="user-pass-123",
        )
        self.url = "/api/superadmin/mail-health/"

        retry = enqueue_transactional_email(
            message_key="health-retry",
            template_key="email.verify",
            recipient="private-recipient@example.com",
            context={"details": "private render context"},
        )
        retry.status = TransactionalEmail.Status.RETRY
        retry.last_error_code = "transport"
        retry.next_attempt_at = timezone.now() + timedelta(minutes=1)
        retry.save(update_fields=["status", "last_error_code", "next_attempt_at", "updated_at"])

        sent = enqueue_transactional_email(
            message_key="health-sent",
            template_key="password.changed",
            recipient="sent-recipient@example.com",
        )
        sent_at = timezone.now()
        sent.status = TransactionalEmail.Status.SENT
        sent.sent_at = sent_at
        sent.recipient = ""
        sent.context = {}
        sent.payload_cleared_at = sent_at
        sent.save(
            update_fields=[
                "status",
                "sent_at",
                "recipient",
                "context",
                "payload_cleared_at",
                "updated_at",
            ]
        )

    def test_anonymous_and_regular_users_cannot_read_mail_health(self):
        anonymous = APIClient().get(self.url)
        self.assertIn(anonymous.status_code, {401, 403})
        self.assertNotIn("counts", str(getattr(anonymous, "data", {})))

        regular = APIClient()
        regular.force_authenticate(self.user)
        response = regular.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("counts", str(response.data))

    def test_superadmin_gets_only_redacted_operational_aggregates(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get(self.url)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            set(response.data),
            {"configured", "counts", "last_success_at", "latency_seconds", "recent_error_classes"},
        )
        self.assertTrue(response.data["configured"])
        self.assertEqual(response.data["counts"][TransactionalEmail.Status.RETRY], 1)
        self.assertEqual(response.data["counts"][TransactionalEmail.Status.SENT], 1)
        self.assertIn("transport", response.data["recent_error_classes"])
        self.assertIsNotNone(response.data["last_success_at"])
        self.assertIn("p50", response.data["latency_seconds"])
        self.assertIn("p95", response.data["latency_seconds"])

        serialized = str(response.data)
        self.assertNotIn("private-recipient@example.com", serialized)
        self.assertNotIn("sent-recipient@example.com", serialized)
        self.assertNotIn("private render context", serialized)
        self.assertNotIn("EMAIL_HOST_PASSWORD", serialized)
