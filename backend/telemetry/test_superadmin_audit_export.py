from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family

from .models import AuditEvent
from .service import record_audit_event


class SuperadminAuditExportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="audit-export-admin", password="pw")
        self.owner = User.objects.create_user(username="audit-export-owner", password="pw")
        self.family = Family.objects.create(name="Audit Export Family", slug="audit-export-family")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _private_event(self):
        return record_audit_event(
            "auth.login.failed",
            actor=self.owner,
            actor_class="user",
            family=self.family,
            outcome="failed",
            reason="invalid_credentials",
            request_id="req-export-1",
            target_type="user",
            target_id=str(self.owner.pk),
            metadata={"auth_method": "password", "identifier_hash": "a" * 64},
            occurred_at=timezone.now() - timedelta(minutes=2),
        )

    def test_csv_export_requires_fresh_reauthentication(self):
        self._private_event()
        response = self.client.get("/api/superadmin/audit/?period=24h&export=csv")
        self.assertEqual(response.status_code, 403)

    def test_csv_export_uses_allow_list_and_audits_itself(self):
        event = self._private_event()
        with patch(
            "telemetry.superadmin_audit_views._enforce_sensitive_action",
            return_value=SimpleNamespace(allowed=True),
        ):
            response = self.client.get(
                f"/api/superadmin/audit/?period=24h&actor_class=user&family_id={self.family.pk}&export=csv"
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertTrue(response["X-Audit-Export-Id"])

        csv_text = response.content.decode("utf-8")
        self.assertIn(str(event.id), csv_text)
        self.assertIn("auth.login.failed", csv_text)
        self.assertIn("auth_method", csv_text)
        self.assertIn("password", csv_text)
        self.assertNotIn("identifier_hash", csv_text)
        self.assertNotIn("a" * 64, csv_text)
        self.assertNotIn("superadmin.export.created", csv_text)

        export_event = AuditEvent.objects.get(event_key="superadmin.export.created")
        self.assertEqual(export_event.actor_id, self.admin.pk)
        self.assertEqual(export_event.actor_class, AuditEvent.ActorClass.SUPERADMIN)
        self.assertEqual(export_event.target_type, "export")
        self.assertEqual(export_event.target_id, response["X-Audit-Export-Id"])
        self.assertEqual(export_event.metadata, {"export_kind": "audit_csv"})

    def test_export_format_and_pagination_combination_fail_closed(self):
        bad_format = self.client.get("/api/superadmin/audit/?export=xlsx")
        self.assertEqual(bad_format.status_code, 400)

        paginated_export = self.client.get("/api/superadmin/audit/?export=csv&limit=10")
        self.assertEqual(paginated_export.status_code, 400)
