from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from family.models import Family, Membership

from .catalog import TelemetrySchemaError
from .models import AuditEvent, DailyRollup, UsageEvent
from .service import (
    METRIC_ACTIVE_FAMILIES,
    METRIC_ACTIVE_USERS,
    METRIC_AUDIT_EVENT_COUNT,
    METRIC_MODULE_USERS,
    prune_raw_events,
    recompute_daily_rollups,
    record_audit_event,
    record_usage_event,
    try_record_audit_event,
)


@override_settings(TELEMETRY_USAGE_RETENTION_DAYS=30, TELEMETRY_AUDIT_RETENTION_DAYS=90)
class TelemetryCoreTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="telemetry-user", password="test-pass-123")
        self.user2 = User.objects.create_user(username="telemetry-user-2", password="test-pass-123")
        self.user3 = User.objects.create_user(username="telemetry-user-3", password="test-pass-123")
        self.family = Family.objects.create(name="Telemetry Family", slug="telemetry-family")
        self.family2 = Family.objects.create(name="Telemetry Family 2", slug="telemetry-family-2")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family, user=self.user2, role=Membership.Role.ADULT)
        Membership.objects.create(family=self.family2, user=self.user3, role=Membership.Role.OWNER)
        self.now = datetime(2026, 10, 10, 12, 34, tzinfo=dt_timezone.utc)

    def test_audit_catalog_rejects_unknown_or_content_metadata(self):
        with self.assertRaises(TelemetrySchemaError):
            record_audit_event(
                "auth.login.failed",
                actor=self.user,
                actor_class="user",
                outcome="failed",
                metadata={"email": "private@example.com"},
                occurred_at=self.now,
            )
        with self.assertRaises(TelemetrySchemaError):
            record_audit_event(
                "auth.login.failed",
                actor=self.user,
                actor_class="user",
                outcome="failed",
                metadata={"identifier_hash": "not-a-digest"},
                occurred_at=self.now,
            )
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_best_effort_audit_wrapper_does_not_break_business_flow(self):
        result = try_record_audit_event(
            "unknown.event",
            actor=self.user,
            actor_class="user",
            outcome="failed",
        )
        self.assertIsNone(result)
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_audit_event_is_append_only(self):
        event = record_audit_event(
            "auth.login.succeeded",
            actor=self.user,
            actor_class="user",
            outcome="success",
            metadata={"auth_method": "password"},
            request_id="req-123",
            occurred_at=self.now,
        )
        event.reason = "user_request"
        with self.assertRaises(ValidationError):
            event.save()

    def test_usage_is_membership_scoped_and_hourly_deduplicated(self):
        first = record_usage_event(
            "activity.foreground",
            user=self.user,
            family=self.family,
            occurred_at=self.now,
        )
        second = record_usage_event(
            "activity.foreground",
            user=self.user,
            family=self.family,
            occurred_at=self.now + timedelta(minutes=20),
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(UsageEvent.objects.count(), 1)

        outsider = get_user_model().objects.create_user(username="outsider", password="test-pass-123")
        with self.assertRaises(TelemetrySchemaError):
            record_usage_event(
                "module.used",
                user=outsider,
                family=self.family,
                dimension_key="tasks",
                occurred_at=self.now,
            )
        with self.assertRaises(TelemetrySchemaError):
            record_usage_event(
                "module.used",
                user=self.user,
                family=self.family,
                dimension_key="free-form-private-title",
                occurred_at=self.now,
            )

    def test_rollups_are_deterministic_and_family_scoped(self):
        for user, family in (
            (self.user, self.family),
            (self.user2, self.family),
            (self.user3, self.family2),
        ):
            record_usage_event("activity.foreground", user=user, family=family, occurred_at=self.now)
        record_usage_event("module.used", user=self.user, family=self.family, dimension_key="tasks", occurred_at=self.now)
        record_usage_event("module.used", user=self.user2, family=self.family, dimension_key="tasks", occurred_at=self.now)
        record_usage_event("module.used", user=self.user, family=self.family, dimension_key="shopping", occurred_at=self.now)
        record_audit_event(
            "auth.login.succeeded",
            actor=self.user,
            actor_class="user",
            outcome="success",
            metadata={"auth_method": "password"},
            occurred_at=self.now,
        )

        day = self.now.date()
        recompute_daily_rollups(day)
        first_snapshot = list(
            DailyRollup.objects.filter(day=day)
            .values_list("metric_key", "family_id", "dimension_key", "value")
            .order_by("metric_key", "family_id", "dimension_key")
        )
        recompute_daily_rollups(day)
        second_snapshot = list(
            DailyRollup.objects.filter(day=day)
            .values_list("metric_key", "family_id", "dimension_key", "value")
            .order_by("metric_key", "family_id", "dimension_key")
        )
        self.assertEqual(first_snapshot, second_snapshot)
        self.assertEqual(
            DailyRollup.objects.get(day=day, metric_key=METRIC_ACTIVE_USERS, family__isnull=True).value,
            3,
        )
        self.assertEqual(
            DailyRollup.objects.get(day=day, metric_key=METRIC_ACTIVE_FAMILIES, family__isnull=True).value,
            2,
        )
        self.assertEqual(
            DailyRollup.objects.get(day=day, metric_key=METRIC_ACTIVE_USERS, family=self.family).value,
            2,
        )
        self.assertEqual(
            DailyRollup.objects.get(
                day=day,
                metric_key=METRIC_MODULE_USERS,
                family__isnull=True,
                dimension_key="tasks",
            ).value,
            2,
        )
        self.assertEqual(
            DailyRollup.objects.get(
                day=day,
                metric_key=METRIC_AUDIT_EVENT_COUNT,
                family__isnull=True,
                dimension_key="auth.login.succeeded:success",
            ).value,
            1,
        )

    def test_retention_prunes_raw_events_but_keeps_rollups(self):
        old_usage = self.now - timedelta(days=31)
        old_audit = self.now - timedelta(days=91)
        record_usage_event("activity.foreground", user=self.user, family=self.family, occurred_at=old_usage)
        record_audit_event(
            "auth.logout",
            actor=self.user,
            actor_class="user",
            outcome="success",
            occurred_at=old_audit,
        )
        recompute_daily_rollups(old_usage.date())
        self.assertTrue(DailyRollup.objects.filter(day=old_usage.date()).exists())

        result = prune_raw_events(now=self.now, batch_size=1)
        self.assertEqual(result["usage_deleted"], 1)
        self.assertEqual(result["audit_deleted"], 1)
        self.assertEqual(UsageEvent.objects.count(), 0)
        self.assertEqual(AuditEvent.objects.count(), 0)
        self.assertTrue(DailyRollup.objects.filter(day=old_usage.date()).exists())
