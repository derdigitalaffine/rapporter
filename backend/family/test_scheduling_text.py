from datetime import date

from django.test import SimpleTestCase

from .scheduling_rules import to_event_recurrence
from .scheduling_text import parse_flexible_scheduling_text


class FlexibleSchedulingTextTests(SimpleTestCase):
    def parse(self, text):
        return parse_flexible_scheduling_text(
            text,
            "Europe/Berlin",
            today=date(2026, 10, 17),
        )

    def test_spelled_out_and_singular_plural_intervals(self):
        self.assertEqual(
            self.parse("Alle drei Tage!")["recurrence"],
            {"frequency": "daily", "interval": 3},
        )
        self.assertEqual(
            self.parse("jede 2 Wochen")["recurrence"],
            {"frequency": "weekly", "interval": 2},
        )
        self.assertEqual(
            self.parse("every three months")["recurrence"],
            {"frequency": "monthly", "interval": 3},
        )

    def test_ordinal_business_day_wording_keeps_true_business_day_counter(self):
        self.assertEqual(
            self.parse("jeden dritten Werktag")["recurrence"],
            {"frequency": "daily", "interval": 3, "business_days": True},
        )
        self.assertEqual(
            self.parse("every three business days")["recurrence"],
            {"frequency": "daily", "interval": 3, "business_days": True},
        )

    def test_bare_weekday_wording_remains_calendar_compatible(self):
        for wording in ("werktags", "Montag bis Freitag", "weekdays", "Monday to Friday"):
            with self.subTest(wording=wording):
                rule = self.parse(wording)
                self.assertEqual(
                    rule["recurrence"],
                    {"frequency": "weekly", "interval": 1, "weekdays": ["MO", "TU", "WE", "TH", "FR"]},
                )
                self.assertEqual(to_event_recurrence(rule, "Europe/Berlin"), rule["recurrence"])

    def test_common_quota_wording_variants(self):
        cases = {
            "zweimal die Woche": {"frequency": "weekly", "interval": 1, "times_per_period": 2},
            "3× monatlich": {"frequency": "monthly", "interval": 1, "times_per_period": 3},
            "2-mal pro Tag": {"frequency": "daily", "interval": 1, "times_per_period": 2},
            "twice a week": {"frequency": "weekly", "interval": 1, "times_per_period": 2},
            "three times per month": {"frequency": "monthly", "interval": 1, "times_per_period": 3},
        }
        for wording, recurrence in cases.items():
            with self.subTest(wording=wording):
                self.assertEqual(self.parse(wording)["recurrence"], recurrence)

    def test_weekday_inflection_and_relaxed_clock_are_understood(self):
        rule = self.parse("montags um 8 Uhr")
        self.assertEqual(rule["recurrence"], {"frequency": "weekly", "weekdays": ["MO"]})
        self.assertEqual(rule["segments"], [{"preferred_time": "08:00"}])

        english = self.parse("Mondays at 8:30")
        self.assertEqual(english["recurrence"], {"frequency": "weekly", "weekdays": ["MO"]})
        self.assertEqual(english["segments"][0]["preferred_time"], "08:30")

    def test_nominative_nth_weekday_is_normalized(self):
        rule = self.parse("erster Montag im Quartal")
        self.assertEqual(
            rule["recurrence"],
            {"frequency": "quarterly", "interval": 1, "nth_weekdays": [{"weekday": "MO", "ordinal": 1}]},
        )

    def test_simple_adverb_forms_map_to_expected_cadence(self):
        cases = {
            "wöchentlich": {"frequency": "weekly", "interval": 1},
            "monatlich": {"frequency": "monthly", "interval": 1},
            "vierteljährlich": {"frequency": "quarterly", "interval": 1},
            "jährlich": {"frequency": "yearly", "interval": 1},
        }
        for wording, recurrence in cases.items():
            with self.subTest(wording=wording):
                self.assertEqual(self.parse(wording)["recurrence"], recurrence)
