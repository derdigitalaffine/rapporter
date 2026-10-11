from datetime import timedelta
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .service import record_audit_event


class SuperadminOnboardingFunnelTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="funnel-admin", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _invite_event(self, event_key, invite_id, *, occurred_at, role=None):
        metadata = {"role": role} if role and event_key in {
            "invite.created",
            "invite.sent",
            "invite.email_failed",
            "invite.accepted",
        } else {}
        return record_audit_event(
            event_key,
            actor_class="system",
            outcome="failed" if event_key == "invite.email_failed" else "success",
            reason="system" if event_key == "invite.email_failed" else "",
            target_type="invite",
            target_id=str(invite_id),
            metadata=metadata,
            occurred_at=occurred_at,
        )

    def test_overview_pairs_invite_transitions_and_compares_created_cohorts(self):
        now = timezone.now()

        accepted_owner = uuid.uuid4()
        self._invite_event("invite.created", accepted_owner, occurred_at=now - timedelta(days=3), role="owner")
        self._invite_event("invite.sent", accepted_owner, occurred_at=now - timedelta(days=2), role="owner")
        self._invite_event("invite.accepted", accepted_owner, occurred_at=now - timedelta(days=1), role="owner")

        failed_adult = uuid.uuid4()
        self._invite_event("invite.created", failed_adult, occurred_at=now - timedelta(days=2), role="adult")
        self._invite_event("invite.sent", failed_adult, occurred_at=now - timedelta(hours=36), role="adult")
        self._invite_event(
            "invite.email_failed",
            failed_adult,
            occurred_at=now - timedelta(hours=30),
            role="adult",
        )

        expired_adult = uuid.uuid4()
        self._invite_event("invite.created", expired_adult, occurred_at=now - timedelta(days=1), role="adult")
        self._invite_event("invite.expired", expired_adult, occurred_at=now - timedelta(hours=2))

        revoked_adult = uuid.uuid4()
        self._invite_event("invite.created", revoked_adult, occurred_at=now - timedelta(hours=18), role="adult")
        self._invite_event("invite.revoked", revoked_adult, occurred_at=now - timedelta(hours=1))

        previous_owner = uuid.uuid4()
        self._invite_event("invite.created", previous_owner, occurred_at=now - timedelta(days=10), role="owner")
        self._invite_event("invite.sent", previous_owner, occurred_at=now - timedelta(days=9), role="owner")
        self._invite_event("invite.accepted", previous_owner, occurred_at=now - timedelta(days=8), role="owner")

        response = self.client.get("/api/superadmin/analytics/overview/?period=7d")

        self.assertEqual(response.status_code, 200, response.data)
        onboarding = response.data["onboarding"]
        funnel = onboarding["invites"]
        self.assertEqual(funnel["created"]["value"], 4)
        self.assertEqual(funnel["created"]["previous"], 1)
        self.assertEqual(funnel["sent"]["value"], 2)
        self.assertEqual(funnel["accepted"]["value"], 1)
        self.assertEqual(funnel["email_failed"]["value"], 1)
        self.assertEqual(funnel["expired"]["value"], 1)
        self.assertEqual(funnel["revoked"]["value"], 1)
        self.assertEqual(funnel["send_to_accept_rate_pct"]["value"], 50.0)
        self.assertEqual(funnel["send_to_accept_rate_pct"]["previous"], 100.0)
        self.assertEqual(funnel["median_seconds_to_accept"]["value"], 172800)
        self.assertEqual(funnel["median_seconds_to_accept"]["previous"], 172800)

        owner = onboarding["owner_invites"]
        self.assertEqual(owner["created"]["value"], 1)
        self.assertEqual(owner["sent"]["value"], 1)
        self.assertEqual(owner["accepted"]["value"], 1)
        self.assertEqual(owner["send_to_accept_rate_pct"]["value"], 100.0)
        self.assertNotIn("expired", owner)
        self.assertNotIn("revoked", owner)

        measurement = onboarding["measurement"]
        self.assertEqual(measurement["opened_or_read"], "not_measured")
        self.assertIn("SMTP sent", measurement["opened_or_read_reason"])

    def test_funnel_does_not_count_unpaired_or_out_of_window_stages(self):
        now = timezone.now()
        current_created = uuid.uuid4()
        self._invite_event("invite.created", current_created, occurred_at=now - timedelta(days=2), role="adult")

        old_created = uuid.uuid4()
        self._invite_event("invite.created", old_created, occurred_at=now - timedelta(days=8), role="adult")
        self._invite_event("invite.sent", old_created, occurred_at=now - timedelta(days=2), role="adult")
        self._invite_event("invite.accepted", old_created, occurred_at=now - timedelta(days=1), role="adult")

        response = self.client.get("/api/superadmin/analytics/overview/?period=7d")

        self.assertEqual(response.status_code, 200, response.data)
        funnel = response.data["onboarding"]["invites"]
        self.assertEqual(funnel["created"]["value"], 1)
        self.assertEqual(funnel["sent"]["value"], 0)
        self.assertEqual(funnel["accepted"]["value"], 0)
        self.assertIsNone(funnel["send_to_accept_rate_pct"]["value"])
        self.assertIsNone(funnel["median_seconds_to_accept"]["value"])

        serialized = str(response.data)
        self.assertNotIn(str(current_created), serialized)
        self.assertNotIn(str(old_created), serialized)
