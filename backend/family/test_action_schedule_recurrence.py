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

    def test_hourly_interval_restarts_after_latest_completion(self):
        schedule = normalize_schedule({
            'mode': 'static',
            'anchor_date': '2026-10-17',
            'recurrence': {'frequency': 'hourly', 'interval': 4},
        }, 'Europe/Berlin')
        now = datetime(2026, 10, 17, 14, 0, tzinfo=UTC)
        completed = datetime(2026, 10, 17, 12, 30, tzinfo=UTC)
        prediction = predict(schedule, [completed], now)
        self.assertEqual(prediction['status'], 'scheduled')
        self.assertEqual(prediction['expected_at'], datetime(2026, 10, 17, 16, 30, tzinfo=UTC))
        due = predict(schedule, [completed], datetime(2026, 10, 17, 17, 0, tzinfo=UTC))
        self.assertEqual(due['status'], 'due')

    def test_hourly_interval_phrases_are_deterministic(self):
        german = parse_schedule('alle 6 Stunden', 'Europe/Berlin', today=date(2026, 10, 17))
        english = parse_schedule('every 8 hours', 'Europe/Berlin', today=date(2026, 10, 17))
        self.assertEqual(german['recurrence'], {'frequency': 'hourly', 'interval': 6})
        self.assertEqual(english['recurrence'], {'frequency': 'hourly', 'interval': 8})

    def test_business_day_interval_counts_only_monday_to_friday(self):
        schedule = parse_schedule('alle 3 Werktage', 'Europe/Berlin', today=date(2026, 10, 19))
        self.assertEqual(schedule['recurrence'], {'frequency': 'daily', 'interval': 3, 'business_days': True})
        monday = predict(schedule, [], datetime(2026, 10, 19, 7, tzinfo=UTC))
        self.assertEqual(monday['expected_at'].date().isoformat(), '2026-10-19')
        after_monday = predict(schedule, [datetime(2026, 10, 19, 8, tzinfo=UTC)], datetime(2026, 10, 19, 9, tzinfo=UTC))
        self.assertEqual(after_monday['expected_at'].date().isoformat(), '2026-10-22')
        after_thursday = predict(schedule, [datetime(2026, 10, 22, 8, tzinfo=UTC)], datetime(2026, 10, 22, 9, tzinfo=UTC))
        self.assertEqual(after_thursday['expected_at'].date().isoformat(), '2026-10-27')

    def test_business_day_anchor_on_weekend_moves_to_monday_and_english_parses(self):
        weekend = parse_schedule('alle 2 Werktage', 'Europe/Berlin', today=date(2026, 10, 17))
        english = parse_schedule('every 4 business days', 'Europe/Berlin', today=date(2026, 10, 17))
        self.assertEqual(english['recurrence'], {'frequency': 'daily', 'interval': 4, 'business_days': True})
        prediction = predict(weekend, [], datetime(2026, 10, 17, 8, tzinfo=UTC))
        self.assertEqual(prediction['expected_at'].date().isoformat(), '2026-10-19')
        with self.assertRaises(ValueError):
            normalize_schedule({'mode': 'static', 'recurrence': {'frequency': 'weekly', 'interval': 2, 'business_days': True}}, 'Europe/Berlin')

    def test_times_per_week_tracks_progress_without_fake_slots(self):
        schedule = normalize_schedule({
            'mode': 'static',
            'anchor_date': '2026-10-12',
            'recurrence': {'frequency': 'weekly', 'interval': 1, 'times_per_period': 3},
        }, 'Europe/Berlin')
        observations = [
            datetime(2026, 10, 12, 18, tzinfo=UTC),
            datetime(2026, 10, 15, 7, tzinfo=UTC),
        ]
        prediction = predict(schedule, observations, datetime(2026, 10, 17, 10, tzinfo=UTC))
        self.assertEqual(prediction['status'], 'due')
        self.assertEqual(prediction['target_count'], 3)
        self.assertEqual(prediction['completed_count'], 2)
        self.assertEqual(prediction['remaining_count'], 1)
        self.assertEqual(prediction['period_start'], '2026-10-12')
        self.assertEqual(prediction['period_end'], '2026-10-18')
        complete = predict(schedule, observations + [datetime(2026, 10, 17, 11, tzinfo=UTC)], datetime(2026, 10, 17, 12, tzinfo=UTC))
        self.assertEqual(complete['status'], 'scheduled')
        self.assertEqual(complete['remaining_count'], 0)
        self.assertEqual(complete['expected_at'].date().isoformat(), '2026-10-19')

    def test_times_per_period_phrases_and_validation(self):
        german = parse_schedule('3 mal pro Woche', 'Europe/Berlin', today=date(2026, 10, 17))
        compact = parse_schedule('2x pro Tag', 'Europe/Berlin', today=date(2026, 10, 17))
        english = parse_schedule('4 times per month', 'Europe/Berlin', today=date(2026, 10, 17))
        self.assertEqual(german['recurrence'], {'frequency': 'weekly', 'interval': 1, 'times_per_period': 3})
        self.assertEqual(compact['recurrence'], {'frequency': 'daily', 'interval': 1, 'times_per_period': 2})
        self.assertEqual(english['recurrence'], {'frequency': 'monthly', 'interval': 1, 'times_per_period': 4})
        with self.assertRaises(ValueError):
            normalize_schedule({'mode': 'static', 'recurrence': {'frequency': 'yearly', 'times_per_period': 2}}, 'Europe/Berlin')
        with self.assertRaises(ValueError):
            normalize_schedule({'mode': 'static', 'recurrence': {'frequency': 'weekly', 'interval': 2, 'times_per_period': 2}}, 'Europe/Berlin')
