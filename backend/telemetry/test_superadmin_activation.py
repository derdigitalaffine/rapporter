from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from family.models import Family, Membership

from .models import AuditEvent, UsageEvent
from .superadmin_activation import activation_overview, rolling_engagement


@override_settings(TELEMETRY_USAGE_RETENTION_DAYS=60, TELEMETRY_AUDIT_RETENTION_DAYS=180)
class SuperadminActivationMetricsTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.family = Family.objects.create(name="Activation Family", slug="activation-family")

    def _user(self, username, joined_at):
        user = self.User.objects.create_user(username=username, password="pw")
        self.User.objects.filter(pk=user.pk).update(date_joined=joined_at)
        user.refresh_from_db()
        Membership.objects.create(family=self.family, user=user, role=Membership.Role.ADULT)
        return user

    def _accept(self, user, at, target_id):
        return AuditEvent.objects.create(
            occurred_at=at,
            event_key="invite.accepted",
            actor=user,
            actor_class=AuditEvent.ActorClass.USER,
            family=self.family,
            outcome=AuditEvent.Outcome.SUCCESS,
            reason="user_request",
            target_type="invite",
            target_id=target_id,
            metadata={"role": "adult"},
        )

    def _verify(self, user, at):
        AuditEvent.objects.create(
            occurred_at=at,
            event_key="auth.email.verified",
            actor=user,
            actor_class=AuditEvent.ActorClass.USER,
            outcome=AuditEvent.Outcome.SUCCESS,
            reason="user_request",
            target_type="user",
            target_id=str(user.pk),
        )

    def _activity(self, user, at):
        UsageEvent.objects.create(
            occurred_at=at,
            bucket_start=at.replace(minute=0, second=0, microsecond=0),
            event_key="activity.foreground",
            user=user,
            family=self.family,
            dimension_key="",
        )

    def test_activation_v1_counts_only_mature_new_invite_accounts(self):
        observation_end = timezone.now() + timedelta(days=20)
        current_start = observation_end - timedelta(days=15)
        previous_start = current_start - timedelta(days=15)
        instrumentation_start = previous_start - timedelta(days=1)

        accepted_at = current_start + timedelta(hours=2)
        activated = self._user("activated", accepted_at - timedelta(minutes=20))
        self._accept(activated, accepted_at, "invite-activated")
        self._verify(activated, accepted_at + timedelta(days=1))
        self._activity(activated, accepted_at + timedelta(days=2))

        no_activity_at = current_start + timedelta(days=1)
        no_activity = self._user("no-activity", no_activity_at - timedelta(minutes=10))
        self._accept(no_activity, no_activity_at, "invite-no-activity")
        self._verify(no_activity, no_activity_at + timedelta(hours=2))

        existing_at = current_start + timedelta(days=2)
        existing = self._user("existing", existing_at - timedelta(days=30))
        self._accept(existing, existing_at, "invite-existing")
        self._verify(existing, existing_at + timedelta(hours=1))
        self._activity(existing, existing_at + timedelta(hours=2))

        pending_at = observation_end - timedelta(days=2)
        pending = self._user("pending", pending_at - timedelta(minutes=15))
        self._accept(pending, pending_at, "invite-pending")
        self._verify(pending, pending_at + timedelta(hours=1))
        self._activity(pending, pending_at + timedelta(hours=2))

        with patch(
            "telemetry.superadmin_activation.EMAIL_VERIFICATION_TELEMETRY_START",
            instrumentation_start,
        ):
            result = activation_overview(
                current_start,
                observation_end,
                previous_start,
                observation_end=observation_end,
            )

        current = result["current"]
        self.assertTrue(current["available"])
        self.assertTrue(current["coverage"]["complete"])
        self.assertEqual(current["accepted_new_accounts"], 3)
        self.assertEqual(current["mature_cohort"], 2)
        self.assertEqual(current["pending_maturity"], 1)
        self.assertEqual(current["email_verified_within_7d"], 2)
        self.assertEqual(current["meaningful_activity_within_7d"], 1)
        self.assertEqual(current["activated_within_7d"], 1)
        self.assertEqual(current["activation_rate_pct"], 50.0)
        self.assertEqual(current["median_seconds_to_activation"], 2 * 24 * 60 * 60)
        self.assertEqual(current["excluded_existing_accounts"], 1)
        self.assertEqual(result["definition"]["version"], "invite_new_account_v1")
        self.assertFalse(result["measurement"]["identifiers_in_response"])
        self.assertNotIn(str(activated.pk), str(result))
        self.assertNotIn("invite-activated", str(result))

    def test_activation_is_fail_closed_without_verification_instrumentation_start(self):
        end = timezone.now()
        start = end - timedelta(days=7)
        result = activation_overview(start, end, start - timedelta(days=7), observation_end=end)
        self.assertFalse(result["current"]["available"])
        self.assertIsNone(result["current"]["activation_rate_pct"])
        self.assertIn(
            "email_verification_instrumentation_start_not_set",
            result["current"]["coverage"]["reasons"],
        )

    def test_activation_reports_forward_only_partial_coverage(self):
        end = timezone.now() + timedelta(days=20)
        start = end - timedelta(days=15)
        instrumentation_start = start + timedelta(days=5)
        with patch(
            "telemetry.superadmin_activation.EMAIL_VERIFICATION_TELEMETRY_START",
            instrumentation_start,
        ):
            result = activation_overview(start, end, start - timedelta(days=15), observation_end=end)
        self.assertTrue(result["current"]["available"])
        self.assertFalse(result["current"]["coverage"]["complete"])
        self.assertEqual(result["current"]["coverage"]["effective_start"], instrumentation_start)
        self.assertIn("email_verification_forward_only", result["current"]["coverage"]["reasons"])

    def test_rolling_engagement_reports_dau_wau_mau_and_retention_coverage(self):
        end = timezone.now()
        user_a = self._user("rolling-a", end - timedelta(days=100))
        user_b = self._user("rolling-b", end - timedelta(days=100))
        user_c = self._user("rolling-c", end - timedelta(days=100))

        self._activity(user_a, end - timedelta(hours=12))
        self._activity(user_b, end - timedelta(days=5))
        self._activity(user_c, end - timedelta(days=20))
        self._activity(user_a, end - timedelta(days=35))

        result = rolling_engagement(end)

        self.assertEqual(result["dau"]["value"], 1)
        self.assertEqual(result["wau"]["value"], 2)
        self.assertEqual(result["mau"]["value"], 3)
        self.assertEqual(result["active_families_7d"]["value"], 1)
        self.assertEqual(result["active_families_30d"]["value"], 1)
        self.assertTrue(result["mau"]["coverage"]["current_complete"])
        self.assertTrue(result["mau"]["coverage"]["comparison_complete"])

    def test_rolling_engagement_uses_one_aggregate_query(self):
        end = timezone.now()
        user = self._user("rolling-query-budget", end - timedelta(days=100))
        self._activity(user, end - timedelta(hours=2))

        with self.assertNumQueries(1):
            result = rolling_engagement(end)

        self.assertEqual(result["dau"]["value"], 1)
        self.assertEqual(
            result["measurement"]["query_shape"],
            "single conditional aggregate query for 1d/7d/30d current and comparison windows",
        )

    @override_settings(TELEMETRY_USAGE_RETENTION_DAYS=30)
    def test_rolling_engagement_does_not_fake_missing_comparison_history(self):
        end = timezone.now()
        user = self._user("rolling-retention", end - timedelta(days=100))
        self._activity(user, end - timedelta(days=1))

        result = rolling_engagement(end)

        self.assertEqual(result["mau"]["value"], 1)
        self.assertIsNone(result["mau"]["previous"])
        self.assertIsNone(result["mau"]["change_pct"])
        self.assertFalse(result["mau"]["coverage"]["comparison_complete"])
