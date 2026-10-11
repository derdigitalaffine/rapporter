from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import PushSubscription
from mailing.models import ManagedSmtpConfig, TransactionalEmail

from .models import AuditEvent


class SuperadminDeliverySummaryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="delivery-admin", password="pw")
        self.owner = User.objects.create_user(username="delivery-owner", password="pw")
        self.client = APIClient()
        ManagedSmtpConfig.objects.create(
            enabled=True,
            host="smtp.example.test",
            from_email="familyos@example.test",
        )

    def _event(self, event_key, *, occurred_at, outcome="success", metadata=None):
        return AuditEvent.objects.create(
            event_key=event_key,
            occurred_at=occurred_at,
            actor=self.owner,
            actor_class=AuditEvent.ActorClass.USER,
            outcome=outcome,
            metadata=metadata or {},
        )

    def _mail(self, suffix, status):
        return TransactionalEmail.objects.create(
            message_key=f"delivery-{suffix}",
            template_key="private-template",
            recipient="private@example.test",
            recipient_hash=f"private-hash-{suffix}",
            context={"secret": "must-not-leak"},
            status=status,
            next_attempt_at=timezone.now(),
        )

    def test_normal_user_cannot_read_delivery_summary(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/superadmin/delivery/summary/")
        self.assertEqual(response.status_code, 403)

    def test_invalid_period_is_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/delivery/summary/?period=13d")
        self.assertEqual(response.status_code, 400)
        self.assertIn("30d", response.data["allowed_periods"])

    def test_summary_aggregates_delivery_health_without_private_payloads(self):
        now = timezone.now()
        self._mail("queued", TransactionalEmail.Status.QUEUED)
        self._mail("retry", TransactionalEmail.Status.RETRY)
        self._mail("failed", TransactionalEmail.Status.FAILED)
        self._mail("sent", TransactionalEmail.Status.SENT)
        PushSubscription.objects.create(
            user=self.owner,
            endpoint="https://push.example.test/private-active-endpoint",
            p256dh="private-p256dh-active",
            auth="private-auth-active",
            active=True,
            last_success_at=now - timedelta(hours=1),
        )
        PushSubscription.objects.create(
            user=self.owner,
            endpoint="https://push.example.test/private-inactive-endpoint",
            p256dh="private-p256dh-inactive",
            auth="private-auth-inactive",
            active=False,
        )

        self._event("mail.sent", occurred_at=now - timedelta(hours=1))
        self._event("mail.sent", occurred_at=now - timedelta(hours=2))
        self._event(
            "mail.failed",
            occurred_at=now - timedelta(hours=3),
            outcome="failed",
            metadata={"error_class": "smtp_timeout"},
        )
        self._event("push.sent", occurred_at=now - timedelta(hours=4))
        self._event(
            "push.failed",
            occurred_at=now - timedelta(hours=5),
            outcome="failed",
            metadata={"error_class": "subscription_invalid"},
        )
        self._event("mail.sent", occurred_at=now - timedelta(days=8))
        self._event(
            "mail.failed",
            occurred_at=now - timedelta(days=9),
            outcome="failed",
            metadata={"error_class": "smtp_timeout"},
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/delivery/summary/?period=7d")

        self.assertEqual(response.status_code, 200)
        mail = response.data["mail"]
        self.assertTrue(mail["smtp_configured"])
        self.assertEqual(mail["current_outbox"]["queued"], 1)
        self.assertEqual(mail["current_outbox"]["retry"], 1)
        self.assertEqual(mail["current_outbox"]["failed"], 1)
        self.assertEqual(mail["current_outbox"]["sent"], 1)
        self.assertEqual(mail["sent"]["value"], 2)
        self.assertEqual(mail["sent"]["previous"], 1)
        self.assertEqual(mail["failed"]["value"], 1)
        self.assertEqual(mail["failed"]["previous"], 1)
        self.assertEqual(mail["success_rate_pct"], 66.7)
        self.assertEqual(mail["failure_classes"], [{"error_class": "smtp_timeout", "count": 1}])
        self.assertIsNotNone(mail["last_successful_delivery"])

        push = response.data["push"]
        self.assertEqual(push["subscriptions"], {"total": 2, "active": 1, "inactive": 1})
        self.assertEqual(push["sent"]["value"], 1)
        self.assertEqual(push["failed"]["value"], 1)
        self.assertEqual(push["success_rate_pct"], 50.0)
        self.assertEqual(
            push["failure_classes"],
            [{"error_class": "subscription_invalid", "count": 1}],
        )

        serialized = str(response.data)
        self.assertNotIn("private@example.test", serialized)
        self.assertNotIn("private-hash", serialized)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("private-template", serialized)
        self.assertNotIn("private-active-endpoint", serialized)
        self.assertNotIn("private-inactive-endpoint", serialized)
        self.assertNotIn("private-p256dh", serialized)
        self.assertNotIn("private-auth", serialized)

    def test_empty_window_does_not_invent_delivery_rates(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/delivery/summary/?period=24h")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["mail"]["success_rate_pct"])
        self.assertIsNone(response.data["push"]["success_rate_pct"])
