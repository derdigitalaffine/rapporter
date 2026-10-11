from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family

from .service import record_audit_event


class SuperadminAuditExplorerTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="audit-admin", password="pw")
        self.owner = User.objects.create_user(username="audit-owner", password="pw")
        self.family = Family.objects.create(name="Audit Family", slug="audit-family")
        self.client = APIClient()

    def test_normal_user_cannot_read_global_audit(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/superadmin/audit/")
        self.assertEqual(response.status_code, 403)

    def test_filters_are_server_side_and_metadata_is_allow_listed(self):
        now = timezone.now()
        record_audit_event(
            "auth.login.failed",
            actor=self.owner,
            actor_class="user",
            family=self.family,
            outcome="failed",
            reason="invalid_credentials",
            request_id="req-audit-1",
            target_type="user",
            target_id=str(self.owner.pk),
            metadata={"auth_method": "password", "identifier_hash": "a" * 64},
            occurred_at=now - timedelta(minutes=5),
        )
        record_audit_event(
            "mail.failed",
            actor_class="system",
            family=self.family,
            outcome="failed",
            reason="system",
            target_type="mail",
            target_id="mail-1",
            metadata={"error_class": "smtp_timeout"},
            occurred_at=now - timedelta(minutes=2),
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f"/api/superadmin/audit/?period=24h&actor_class=user&outcome=failed&family_id={self.family.pk}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pagination"]["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        item = response.data["results"][0]
        self.assertEqual(item["event_key"], "auth.login.failed")
        self.assertEqual(item["details"], {"auth_method": "password"})
        self.assertNotIn("identifier_hash", item["details"])
        self.assertNotIn("metadata", item)
        self.assertEqual(item["request_id"], "req-audit-1")

    def test_invalid_filters_and_pagination_are_rejected(self):
        self.client.force_authenticate(self.admin)
        for query in (
            "period=all",
            "actor_class=robot",
            "outcome=maybe",
            "event_key=unknown.event",
            "target_type=secret",
            "family_id=nope",
            "actor_id=nope",
            "limit=0",
            "limit=101",
            "offset=10001",
        ):
            with self.subTest(query=query):
                response = self.client.get(f"/api/superadmin/audit/?{query}")
                self.assertEqual(response.status_code, 400)

    def test_pagination_is_bounded_and_stable(self):
        now = timezone.now()
        for index in range(3):
            record_audit_event(
                "mail.failed",
                actor_class="system",
                outcome="failed",
                reason="system",
                target_type="mail",
                target_id=f"mail-{index}",
                metadata={"error_class": "smtp_timeout"},
                occurred_at=now - timedelta(minutes=index + 1),
            )

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/audit/?period=24h&limit=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pagination"]["count"], 3)
        self.assertEqual(response.data["pagination"]["next_offset"], 2)
        self.assertEqual(len(response.data["results"]), 2)
