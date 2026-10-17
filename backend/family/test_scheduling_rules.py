from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from .scheduling_rules import (
    VERSION,
    describe_scheduling_rule,
    from_action_schedule,
    from_event_recurrence,
    normalize_scheduling_rule,
    parse_scheduling_text,
    preview_occurrence_dates,
    to_action_schedule,
    to_event_recurrence,
)


BERLIN = ZoneInfo("Europe/Berlin")


class SchedulingRuleTests(SimpleTestCase):
    def test_deterministic_parser_uses_existing_quarter_rule_vocabulary(self):
        rule = parse_scheduling_text(
            "immer am ersten Montag im Quartal",
            "Europe/Berlin",
            today=date(2026, 1, 10),
        )
        self.assertEqual(rule["version"], VERSION)
        self.assertEqual(rule["time_mode"], "wall_clock")
        self.assertEqual(
            rule["recurrence"],
            {"frequency": "quarterly", "interval": 1, "nth_weekdays": [{"weekday": "MO", "ordinal": 1}]},
        )
        self.assertIn("ersten Montag", describe_scheduling_rule(rule, "Europe/Berlin", "de"))

    def test_deterministic_parser_supports_year_month_ordinal(self):
        rule = parse_scheduling_text(
            "immer am letzten Donnerstag im November",
            "Europe/Berlin",
            today=date(2026, 1, 10),
        )
        self.assertEqual(rule["recurrence"]["frequency"], "yearly")
        self.assertEqual(rule["recurrence"]["months"], [11])
        self.assertEqual(rule["recurrence"]["nth_weekdays"], [{"weekday": "TH", "ordinal": -1}])

    def test_static_action_schedule_round_trips_through_canonical_rule(self):
        existing = {
            "version": "action-schedule-v1",
            "timezone": "Europe/Berlin",
            "mode": "static",
            "anchor_date": "2026-10-14",
            "recurrence": {"frequency": "weekly", "interval": 1, "weekdays": ["MO", "TH"]},
            "segments": [{"weekdays": ["MO", "TH"], "preferred_time": "18:00"}],
        }
        rule = from_action_schedule(existing, "Europe/Berlin")
        restored = to_action_schedule(rule, "Europe/Berlin")
        self.assertEqual(restored["recurrence"], existing["recurrence"])
        self.assertEqual(restored["segments"], existing["segments"])
        self.assertEqual(restored["anchor_date"], existing["anchor_date"])

    def test_legacy_and_structured_event_rules_share_the_canonical_adapter(self):
        start = datetime(2026, 10, 14, 9, 0, tzinfo=BERLIN)
        legacy = from_event_recurrence("weekly", start, "Europe/Berlin")
        self.assertEqual(legacy["anchor_date"], "2026-10-14")
        self.assertEqual(legacy["recurrence"], {"frequency": "weekly", "interval": 1})

        structured = from_event_recurrence(
            {"frequency": "yearly", "interval": 1, "nth_weekdays": [{"weekday": "TH", "ordinal": -1}]},
            datetime(2026, 11, 10, 9, 0, tzinfo=BERLIN),
            "Europe/Berlin",
        )
        self.assertEqual(structured["recurrence"]["months"], [11])
        self.assertEqual(to_event_recurrence(structured, "Europe/Berlin"), structured["recurrence"])

    def test_preview_applies_bounds_pauses_includes_and_exclusions(self):
        rule = normalize_scheduling_rule(
            {
                "recurrence": {"frequency": "weekly", "interval": 1, "weekdays": ["MO"]},
                "anchor_date": "2026-01-05",
                "bounds": {"start_on": "2026-01-05", "end_on": "2026-01-31"},
                "pauses": [{"start_on": "2026-01-12", "end_on": "2026-01-12"}],
                "include_dates": ["2026-01-14"],
                "exclude_dates": ["2026-01-19"],
            },
            "Europe/Berlin",
        )
        self.assertEqual(
            preview_occurrence_dates(rule, "Europe/Berlin", after="2026-01-01", limit=10),
            ["2026-01-05", "2026-01-14", "2026-01-26"],
        )

    def test_count_bound_is_applied_before_a_later_preview_window(self):
        rule = normalize_scheduling_rule(
            {
                "recurrence": {"frequency": "daily", "interval": 1},
                "anchor_date": "2026-01-01",
                "bounds": {"count": 3},
            },
            "Europe/Berlin",
        )
        self.assertEqual(preview_occurrence_dates(rule, "Europe/Berlin", after="2026-01-03", limit=5), ["2026-01-03"])
        self.assertEqual(preview_occurrence_dates(rule, "Europe/Berlin", after="2026-01-04", limit=5), [])

    def test_unrepresentable_universal_features_are_never_silently_dropped(self):
        rule = normalize_scheduling_rule(
            {
                "recurrence": {"frequency": "monthly", "interval": 1},
                "anchor_date": "2026-01-01",
                "bounds": {"count": 4},
            },
            "Europe/Berlin",
        )
        with self.assertRaisesRegex(ValueError, "scheduling runtime"):
            to_action_schedule(rule, "Europe/Berlin")
        with self.assertRaisesRegex(ValueError, "scheduling runtime"):
            to_event_recurrence(rule, "Europe/Berlin")

    def test_invalid_time_mode_and_overlapping_explicit_dates_are_rejected(self):
        base = {"recurrence": {"frequency": "daily", "interval": 1}, "anchor_date": "2026-01-01"}
        with self.assertRaisesRegex(ValueError, "time mode"):
            normalize_scheduling_rule({**base, "time_mode": "floating-ish"}, "Europe/Berlin")
        with self.assertRaisesRegex(ValueError, "both explicitly included and excluded"):
            normalize_scheduling_rule(
                {**base, "include_dates": ["2026-01-02"], "exclude_dates": ["2026-01-02"]},
                "Europe/Berlin",
            )

    def test_business_day_rule_has_real_weekday_preview_and_clear_summary(self):
        rule = parse_scheduling_text("alle 3 Werktage", "Europe/Berlin", today=date(2026, 10, 19))
        self.assertEqual(rule["recurrence"], {"frequency": "daily", "interval": 3, "business_days": True})
        self.assertEqual(describe_scheduling_rule(rule, "Europe/Berlin", "de"), "Alle 3 Werktage")
        self.assertEqual(
            preview_occurrence_dates(rule, "Europe/Berlin", after="2026-10-19", limit=4),
            ["2026-10-19", "2026-10-22", "2026-10-27", "2026-10-30"],
        )
        with self.assertRaisesRegex(ValueError, "Action cadence"):
            to_event_recurrence(rule, "Europe/Berlin")

    def test_hourly_and_period_targets_are_described_without_fake_occurrences(self):
        hourly = parse_scheduling_text("alle 6 Stunden", "Europe/Berlin", today=date(2026, 10, 17))
        quota = parse_scheduling_text("3 mal pro Woche", "Europe/Berlin", today=date(2026, 10, 17))
        self.assertEqual(describe_scheduling_rule(hourly, "Europe/Berlin", "de"), "Alle 6 Stunden")
        self.assertEqual(describe_scheduling_rule(quota, "Europe/Berlin", "de"), "3-mal pro Woche")
        self.assertEqual(preview_occurrence_dates(hourly, "Europe/Berlin", after="2026-10-17", limit=5), [])
        self.assertEqual(preview_occurrence_dates(quota, "Europe/Berlin", after="2026-10-17", limit=5), [])
        with self.assertRaisesRegex(ValueError, "Action cadence"):
            to_event_recurrence(hourly, "Europe/Berlin")
        with self.assertRaisesRegex(ValueError, "Action cadence"):
            to_event_recurrence(quota, "Europe/Berlin")
