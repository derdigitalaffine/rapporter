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

    def test_number_words_and_numeric_forms_normalize_identically(self):
        equivalent_groups = [
            ("alle 3 Tage", "alle drei Tage", "jeden 3. Tag", "jeden dritten Tag"),
            ("alle 3 Werktage", "alle drei Werktage", "jeden dritten Werktag"),
            ("alle 2 Wochen", "alle zwei Wochen", "jede zweite Woche"),
            ("alle 6 Stunden", "alle sechs Stunden"),
            ("2x pro Tag", "2 x pro Tag", "2× pro Tag", "2-mal pro Tag", "zweimal pro Tag"),
        ]
        for variants in equivalent_groups:
            with self.subTest(variants=variants):
                expected = self.parse(variants[0])["recurrence"]
                for wording in variants[1:]:
                    self.assertEqual(self.parse(wording)["recurrence"], expected)

    def test_ordinal_business_day_wording_keeps_true_business_day_counter(self):
        expected = {"frequency": "daily", "interval": 3, "business_days": True}
        for wording in (
            "jeden dritten Werktag",
            "every three business days",
            "every third business day",
        ):
            with self.subTest(wording=wording):
                self.assertEqual(self.parse(wording)["recurrence"], expected)

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
            "4 mal im Monat": {"frequency": "monthly", "interval": 1, "times_per_period": 4},
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

        for wording in ("immer montags", "Mondays", "on Mondays"):
            with self.subTest(wording=wording):
                self.assertEqual(self.parse(wording)["recurrence"], {"frequency": "weekly", "weekdays": ["MO"]})

        english = self.parse("Mondays at 8:30")
        self.assertEqual(english["recurrence"], {"frequency": "weekly", "weekdays": ["MO"]})
        self.assertEqual(english["segments"][0]["preferred_time"], "08:30")

    def test_every_nth_weekday_variants_use_weekly_interval(self):
        expected = {"frequency": "weekly", "interval": 2, "weekdays": ["MO"]}
        for wording in ("jeden zweiten Montag", "jeden 2. Montag", "every second Monday", "every other Monday"):
            with self.subTest(wording=wording):
                self.assertEqual(self.parse(wording)["recurrence"], expected)

    def test_english_ordinal_and_other_intervals(self):
        cases = {
            "every third day": {"frequency": "daily", "interval": 3},
            "every 3 days": {"frequency": "daily", "interval": 3},
            "every other week": {"frequency": "weekly", "interval": 2},
            "every 6 hours": {"frequency": "hourly", "interval": 6},
        }
        for wording, recurrence in cases.items():
            with self.subTest(wording=wording):
                self.assertEqual(self.parse(wording)["recurrence"], recurrence)

    def test_nominative_nth_weekday_is_normalized(self):
        rule = self.parse("erster Montag im Quartal")
        self.assertEqual(
            rule["recurrence"],
            {"frequency": "quarterly", "interval": 1, "nth_weekdays": [{"weekday": "MO", "ordinal": 1}]},
        )

    def test_existing_article_based_interval_phrase_is_preserved(self):
        rule = self.parse("alle zwei Monate an einem ersten Montag")
        self.assertEqual(
            rule["recurrence"],
            {"frequency": "monthly", "interval": 2, "nth_weekdays": [{"weekday": "MO", "ordinal": 1}]},
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
