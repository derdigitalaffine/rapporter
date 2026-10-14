from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from .calendar_recurrence import normalize_event_recurrence, recurrence_dict


class CalendarDailyRecurrenceTests(SimpleTestCase):
    def test_daily_structured_rule_is_supported_for_shared_editor(self):
        start = datetime(2026, 10, 14, 9, 0, tzinfo=ZoneInfo("Europe/Berlin"))
        recurrence = normalize_event_recurrence(
            {"frequency": "daily", "interval": 2},
            start,
            "Europe/Berlin",
        )
        self.assertEqual(recurrence, {"frequency": "daily", "interval": 2})
        self.assertEqual(recurrence_dict(recurrence), recurrence)
