from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_identity.models import EmailIdentity
from family.models import Family, Membership

from .models import DailyRollup, UsageEvent
from .service import METRIC_ACTIVE_FAMILIES, METRIC_ACTIVE_USERS


class SuperadminAnalyticsOverviewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="analytics-admin", password="pw")
        self.owner = User.objects.create_user(username="analytics-owner", password="pw")
        self.other = User.objects.create_user(username="analytics-other", password="pw")
        self.family = Family.objects.create(name="Analytics", slug="analytics", status=Family.Status.ACTIVE)
        self.other_family = Family.objects.create(name="Analytics Other", slug="analytics-other", status=Family.Status.SUSPENDED)
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        Membership.objects.create(family=self.family, user=self.other, role=Membership.Role.ADULT, display_name="Other")
        EmailIdentity.objects.create(
            user=self.owner,
            kind=EmailIdentity.Kind.PRIMARY,
            email="owner@example.test",
            email_normalized="owner@example.test",
            verified_at=timezone.now(),
        )
        self.client = APIClient()

    def test_normal_user_cannot_read_global_analytics(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/superadmin/analytics/overview/")
        self.assertEqual(response.status_code, 403)

    def test_invalid_period_is_rejected(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/analytics/overview/?period=13d")
        self.assertEqual(response.status_code, 400)
        self.assertIn("30d", response.data["allowed_periods"])

    def test_overview_uses_distinct_activity_and_rollup_series(self):
        now = timezone.now()
        current_bucket = now.replace(minute=0, second=0, microsecond=0)
        previous_bucket = current_bucket - timedelta(days=31)
        UsageEvent.objects.create(
            user=self.owner,
            family=self.family,
            event_key="activity.foreground",
            bucket_start=current_bucket,
            occurred_at=now - timedelta(hours=2),
            dimension_key="",
        )
        UsageEvent.objects.create(
            user=self.other,
            family=self.family,
            event_key="activity.foreground",
            bucket_start=current_bucket - timedelta(hours=1),
            occurred_at=now - timedelta(hours=1),
            dimension_key="",
        )
        UsageEvent.objects.create(
            user=self.owner,
            family=self.family,
            event_key="activity.foreground",
            bucket_start=previous_bucket,
            occurred_at=now - timedelta(days=31),
            dimension_key="",
        )
        DailyRollup.objects.create(day=now.date(), metric_key=METRIC_ACTIVE_USERS, value=2)
        DailyRollup.objects.create(day=now.date(), metric_key=METRIC_ACTIVE_FAMILIES, value=1)

        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/analytics/overview/?period=30d")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["totals"]["families"], {"total": 2, "active": 1, "suspended": 1})
        self.assertGreaterEqual(response.data["totals"]["users"], 3)
        self.assertEqual(response.data["totals"]["verified_email_users"], 1)
        self.assertEqual(response.data["activity"]["active_users"]["value"], 2)
        self.assertEqual(response.data["activity"]["active_users"]["previous"], 1)
        self.assertEqual(response.data["activity"]["active_users"]["change_pct"], 100.0)
        self.assertEqual(response.data["activity"]["active_families"]["value"], 1)
        self.assertEqual(response.data["timeseries"], [{"day": now.date().isoformat(), "active_users": 2, "active_families": 1}])
        self.assertNotIn("email", response.data["definitions"])

    def test_zero_previous_value_has_no_fake_percentage(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/superadmin/analytics/overview/?period=7d")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["activity"]["active_users"]["change_pct"])
        self.assertIsNone(response.data["activity"]["active_families"]["change_pct"])
