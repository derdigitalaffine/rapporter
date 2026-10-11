from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family, IntegrationSource
from mailing.models import TransactionalEmail

from .models import AuditEvent, DailyRollup


class SuperadminOperationsHealthTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="ops-admin", password="pw")
        self.owner = User.objects.create_user(username="ops-owner", password="pw")
        self.family = Family.objects.create(name="Ops Family", slug="ops-family")
        self.client = APIClient()

    def test_normal_user_cannot_read_operations_health(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/superadmin/operations/health/")
        self.assertEqual(response.status_code, 403)

    def test_health_uses_aggregate_sources_and_keeps_missing_heartbeats_unknown(self):
        now = timezone.now()
        IntegrationSource.objects.create(
            family=self.family,
            name="Private integration",
            kind=IntegrationSource.Kind.GENERIC,
            endpoint="https://integration.example.test/private-token-path",
            config={"api_token": "must-not-leak"},
            enabled=True,
            last_sync_status="failed",
            consecutive_failures=2,
            last_success_at=now - timedelta(hours=2),
        )
        TransactionalEmail.objects.create(
            message_key="ops-private-mail",
            template_key="email.verify",
            recipient="private@example.test",
            recipient_hash="private-recipient-hash",
            context={"details": "must-not-leak"},
            status=TransactionalEmail.Status.RETRY,
            next_attempt_at=now,
            last_error_code="transport",
        )
        AuditEvent.objects.create(
            occurred_at=now - timedelta(minutes=5),
            event_key="mail.failed",
            actor_class=AuditEvent.ActorClass.SYSTEM,
            outcome=AuditEvent.Outcome.FAILED,
            metadata={"error_class": "transport", "private": "must-not-leak"},
        )
        DailyRollup.objects.create(
            day=now.date(),
            metric_key="active.users",
            value=3,
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/operations/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "degraded")
        components = response.data["components"]
        self.assertEqual(components["database"]["status"], "healthy")
        self.assertEqual(components["migrations"]["pending_count"], 0)
        self.assertEqual(components["integrations"]["status"], "degraded")
        self.assertEqual(components["integrations"]["enabled"], 1)
        self.assertEqual(components["integrations"]["degraded"], 1)
        self.assertEqual(components["mail_queue"]["status"], "degraded")
        self.assertEqual(components["mail_queue"]["backlog"], 1)
        self.assertEqual(components["telemetry"]["status"], "healthy")
        for worker in ("scheduler", "notification_worker", "mail_worker", "ocr_worker"):
            self.assertEqual(components["workers"][worker]["status"], "unknown")
            self.assertEqual(components["workers"][worker]["reason"], "no_canonical_heartbeat_source")

        serialized = str(response.data)
        self.assertNotIn("private-token-path", serialized)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("private@example.test", serialized)
        self.assertNotIn("private-recipient-hash", serialized)

    def test_empty_operational_sources_are_not_invented_as_worker_health(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/operations/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["components"]["integrations"]["status"], "unknown")
        self.assertEqual(response.data["components"]["telemetry"]["status"], "unknown")
        self.assertEqual(response.data["components"]["workers"]["mail_worker"]["status"], "unknown")
