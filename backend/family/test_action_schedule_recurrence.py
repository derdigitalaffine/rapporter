from datetime import date, datetime, timezone as dt_timezone

from django.test import SimpleTestCase

from .action_schedule import normalize_schedule, parse_schedule, predict


UTC = dt_timezone.utc


class AdvancedScheduleRecurrenceTests(SimpleTestCase):
    def test_first_monday_of_month_phrase(self):
        schedule = parse_schedule(
            'immer am ersten Montag im Monat',
            'Europe/Berlin',
            today=date(2026, 10, 14),
        )
        self.assertEqual(schedule['recurrence'], {
            'frequency': 'monthly',
            'interval': 1,
            'nth_weekdays': [{'weekday': 'MO', 'ordinal': 1}],
        })
        prediction = predict(schedule, [], datetime(2026, 10, 14, tzinfo=UTC))
        self.assertEqual(prediction['expected_at'].date().isoformat(), '2026-11-02')

    def test_first_monday_of_calendar_quarter_is_not_anchor_relative(self):
        schedule = parse_schedule(
            'immer am ersten Montag im Quartal',
            'Europe/Berlin',
            today=date(2026, 2, 15),
        )
        prediction = predict(schedule, [], datetime(2026, 2, 16, tzinfo=UTC))
        self.assertEqual(schedule['recurrence']['frequency'], 'quarterly')
        self.assertEqual(prediction['expected_at'].date().isoformat(), '2026-04-06')

    def test_quarter_interval_is_counted_in_calendar_quarters(self):
        schedule = normalize_schedule({
            'mode': 'static',
            'anchor_date': '2026-02-15',
            'recurrence': {
                'frequency': 'quarterly',
                'interval': 2,
                'nth_weekdays': [{'weekday': 'MO', 'ordinal': 1}],
            },
        }, 'Europe/Berlin')
        prediction = predict(schedule, [], datetime(2026, 3, 1, tzinfo=UTC))
        self.assertEqual(prediction['expected_at'].date().isoformat(), '2026-07-06')

    def test_last_thursday_in_november_phrase(self):
        schedule = parse_schedule(
            'immer am letzten Donnerstag im November',
            'Europe/Berlin',
            today=date(2026, 1, 1),
        )
        self.assertEqual(schedule['recurrence']['months'], [11])
        prediction = predict(schedule, [], datetime(2026, 1, 2, tzinfo=UTC))
        self.assertEqual(prediction['expected_at'].date().isoformat(), '2026-11-26')

    def test_first_weekend_of_quarter_is_due_once_at_weekend_start(self):
        schedule = parse_schedule(
            'immer das erste Wochenende im Quartal',
            'Europe/Berlin',
            today=date(2026, 4, 1),
        )
        self.assertEqual(schedule['recurrence']['nth_weekdays'], [{'weekday': 'SA', 'ordinal': 1}])
        prediction = predict(schedule, [], datetime(2026, 4, 1, tzinfo=UTC))
        self.assertEqual(prediction['expected_at'].date().isoformat(), '2026-04-04')

    def test_english_advanced_phrases(self):
        quarter = parse_schedule('every first Monday of the quarter', 'Europe/Berlin', today=date(2026, 1, 1))
        november = parse_schedule('every last Thursday in November', 'Europe/Berlin', today=date(2026, 1, 1))
        weekend = parse_schedule('every first weekend of the quarter', 'Europe/Berlin', today=date(2026, 1, 1))
        self.assertEqual(quarter['recurrence']['frequency'], 'quarterly')
        self.assertEqual(november['recurrence']['months'], [11])
        self.assertEqual(weekend['recurrence']['nth_weekdays'][0], {'weekday': 'SA', 'ordinal': 1})
