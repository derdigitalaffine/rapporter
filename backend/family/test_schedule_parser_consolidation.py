from datetime import date

from django.test import SimpleTestCase

from .action_schedule import parse_schedule
from .scheduling_rules import from_action_schedule, parse_scheduling_text, to_event_recurrence
from .scheduling_text import parse_flexible_scheduling_text


class CanonicalScheduleParserTests(SimpleTestCase):
    timezone = "Europe/Berlin"
    today = date(2026, 10, 17)

    def parse(self, text):
        return parse_schedule(text, self.timezone, today=self.today)

    def recurrence(self, text):
        return self.parse(text)["recurrence"]

    def test_number_words_numeric_and_ordinal_intervals_share_one_grammar(self):
        groups = [
            ("alle 3 Tage", "Alle drei Tage!", "jeden 3. Tag", "jeden dritten Tag", "every 3 days", "every third day"),
            ("alle 2 Wochen", "alle zwei Wochen", "jede zweite Woche", "every 2 weeks", "every other week"),
            ("alle 6 Stunden", "alle sechs Stunden", "every 6 hours"),
        ]
        for variants in groups:
            with self.subTest(variants=variants):
                expected = self.recurrence(variants[0])
                for wording in variants[1:]:
                    self.assertEqual(self.recurrence(wording), expected)

    def test_bare_weekday_language_is_calendar_compatible(self):
        expected = {
            "frequency": "weekly",
            "interval": 1,
            "weekdays": ["MO", "TU", "WE", "TH", "FR"],
        }
        for wording in ("werktags", "Montag bis Freitag", "weekdays", "Monday to Friday", "every business day"):
            with self.subTest(wording=wording):
                schedule = self.parse(wording)
                self.assertEqual(schedule["recurrence"], expected)
                rule = from_action_schedule(schedule, self.timezone)
                self.assertEqual(to_event_recurrence(rule, self.timezone), expected)

    def test_explicit_business_day_intervals_keep_action_only_counter(self):
        expected = {"frequency": "daily", "interval": 3, "business_days": True}
        for wording in (
            "alle 3 Werktage",
            "alle drei Werktage",
            "jeden dritten Werktag",
            "every 3 business days",
            "every third business day",
        ):
            with self.subTest(wording=wording):
                schedule = self.parse(wording)
                self.assertEqual(schedule["recurrence"], expected)
                with self.assertRaises(ValueError):
                    to_event_recurrence(from_action_schedule(schedule, self.timezone), self.timezone)

    def test_weekday_inflections_and_intervals_are_canonical(self):
        monday = {"frequency": "weekly", "weekdays": ["MO"]}
        for wording in ("jeden Montag", "montags", "immer montags", "every Monday", "on Mondays"):
            with self.subTest(wording=wording):
                self.assertEqual(self.recurrence(wording), monday)

        alternate = {"frequency": "weekly", "interval": 2, "weekdays": ["MO"]}
        for wording in ("jeden zweiten Montag", "jeden 2. Montag", "every second Monday", "every other Monday"):
            with self.subTest(wording=wording):
                self.assertEqual(self.recurrence(wording), alternate)

    def test_relaxed_clock_suffix_is_normalized_before_schedule_validation(self):
        schedule = self.parse("montags um 8 Uhr")
        self.assertEqual(schedule["recurrence"], {"frequency": "weekly", "weekdays": ["MO"]})
        self.assertEqual(schedule["segments"], [{"preferred_time": "08:00"}])

        english = self.parse("Mondays at 8:30")
        self.assertEqual(english["recurrence"], {"frequency": "weekly", "weekdays": ["MO"]})
        self.assertEqual(english["segments"], [{"preferred_time": "08:30"}])

    def test_flexible_targets_share_the_same_parser(self):
        cases = {
            "2x pro Tag": {"frequency": "daily", "interval": 1, "times_per_period": 2},
            "2 x pro Tag": {"frequency": "daily", "interval": 1, "times_per_period": 2},
            "2× pro Tag": {"frequency": "daily", "interval": 1, "times_per_period": 2},
            "2-mal pro Tag": {"frequency": "daily", "interval": 1, "times_per_period": 2},
            "zweimal die Woche": {"frequency": "weekly", "interval": 1, "times_per_period": 2},
            "dreimal pro Woche": {"frequency": "weekly", "interval": 1, "times_per_period": 3},
            "4 mal im Monat": {"frequency": "monthly", "interval": 1, "times_per_period": 4},
            "twice a day": {"frequency": "daily", "interval": 1, "times_per_period": 2},
            "three times a week": {"frequency": "weekly", "interval": 1, "times_per_period": 3},
        }
        for wording, expected in cases.items():
            with self.subTest(wording=wording):
                self.assertEqual(self.recurrence(wording), expected)

    def test_ordinal_period_targets_keep_existing_semantics(self):
        expected = {
            "frequency": "quarterly",
            "interval": 1,
            "nth_weekdays": [{"weekday": "MO", "ordinal": 1}],
        }
        for wording in (
            "erster Montag im Quartal",
            "am ersten Montag im Quartal",
            "immer am ersten Montag im Quartal",
            "first Monday of the quarter",
            "every first Monday of the quarter",
        ):
            with self.subTest(wording=wording):
                self.assertEqual(self.recurrence(wording), expected)

    def test_preview_adapter_and_legacy_wrapper_have_parser_parity(self):
        phrases = (
            "alle drei Tage",
            "jeden zweiten Montag",
            "zweimal die Woche",
            "Monday to Friday",
            "erster Montag im Quartal",
        )
        for wording in phrases:
            with self.subTest(wording=wording):
                direct = from_action_schedule(self.parse(wording), self.timezone)
                self.assertEqual(parse_scheduling_text(wording, self.timezone, today=self.today), direct)
                self.assertEqual(parse_flexible_scheduling_text(wording, self.timezone, today=self.today), direct)

    def test_unsupported_text_still_fails_explicitly(self):
        with self.assertRaises(ValueError):
            self.parse("irgendwann wenn es passt")
