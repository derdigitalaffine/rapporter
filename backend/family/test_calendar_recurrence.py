from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership


BERLIN = ZoneInfo("Europe/Berlin")


def as_local(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(BERLIN)


class CalendarRecurrenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="calendar-recurrence")
        self.family = Family.objects.create(name="Recurring", slug="recurring", timezone="Europe/Berlin")
        Membership.objects.create(user=self.user, family=self.family, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def rows(self, response):
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        return response.data.get("results", response.data) if isinstance(response.data, dict) else response.data

    def event(self, recurrence, start, end=None, payload=None):
        return FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Serie",
            starts_at=start,
            ends_at=end,
            payload={"provider": "FamilyOS", "recurrence": recurrence, **(payload or {})},
        )

    def test_first_monday_of_calendar_quarter_projects_master_into_range(self):
        master = self.event(
            {"frequency": "quarterly", "interval": 1, "nth_weekdays": [{"weekday": "MO", "ordinal": 1}]},
            datetime(2026, 2, 15, 10, 0, tzinfo=BERLIN),
            datetime(2026, 2, 15, 11, 0, tzinfo=BERLIN),
        )
        rows = self.rows(self.client.get(f"/api/events/?family={self.family.id}&start=2026-04-01&end=2026-06-30&birthdays=0"))
        series = [row for row in rows if row["id"] == str(master.id)]
        self.assertEqual(len(series), 1)
        occurrence = series[0]
        self.assertEqual(occurrence["recurrence_master_id"], str(master.id))
        self.assertEqual(as_local(occurrence["starts_at"]).isoformat(), "2026-04-06T10:00:00+02:00")
        self.assertEqual(as_local(occurrence["ends_at"]).isoformat(), "2026-04-06T11:00:00+02:00")

    def test_last_thursday_in_november_and_first_weekend_of_quarter(self):
        november = self.event(
            {"frequency": "yearly", "interval": 1, "months": [11], "nth_weekdays": [{"weekday": "TH", "ordinal": -1}]},
            datetime(2026, 1, 10, 9, 0, tzinfo=BERLIN),
        )
        weekend = self.event(
            {"frequency": "quarterly", "interval": 1, "nth_weekdays": [{"weekday": "SA", "ordinal": 1}]},
            datetime(2026, 1, 10, 12, 0, tzinfo=BERLIN),
        )
        rows = self.rows(self.client.get(f"/api/events/?family={self.family.id}&start=2026-01-01&end=2026-12-31&birthdays=0"))
        november_rows = [row for row in rows if row["id"] == str(november.id)]
        weekend_rows = [row for row in rows if row["id"] == str(weekend.id)]
        self.assertEqual([as_local(row["starts_at"]).date().isoformat() for row in november_rows], ["2026-11-26"])
        self.assertEqual(
            [as_local(row["starts_at"]).date().isoformat() for row in weekend_rows],
            ["2026-04-04", "2026-07-04", "2026-10-03"],
        )

    def test_legacy_weekly_string_preserves_wall_time_across_dst(self):
        master = self.event(
            "weekly",
            datetime(2026, 3, 22, 10, 0, tzinfo=BERLIN),
            datetime(2026, 3, 22, 11, 30, tzinfo=BERLIN),
        )
        rows = self.rows(self.client.get(f"/api/events/?family={self.family.id}&start=2026-03-29&end=2026-03-29&birthdays=0"))
        occurrence = next(row for row in rows if row["id"] == str(master.id))
        self.assertEqual(as_local(occurrence["starts_at"]).isoformat(), "2026-03-29T10:00:00+02:00")
        self.assertEqual(as_local(occurrence["ends_at"]).isoformat(), "2026-03-29T11:30:00+02:00")

    def test_all_day_civil_dates_shift_with_occurrence(self):
        master = self.event(
            {"frequency": "quarterly", "interval": 1, "nth_weekdays": [{"weekday": "SA", "ordinal": 1}]},
            datetime(2026, 1, 3, 0, 0, tzinfo=BERLIN),
            datetime(2026, 1, 5, 0, 0, tzinfo=BERLIN),
            {"all_day": True, "date_start": "2026-01-03", "date_end_exclusive": "2026-01-05"},
        )
        rows = self.rows(self.client.get(f"/api/events/?family={self.family.id}&start=2026-04-01&end=2026-04-30&birthdays=0"))
        occurrence = next(row for row in rows if row["id"] == str(master.id))
        self.assertEqual(occurrence["payload"]["date_start"], "2026-04-04")
        self.assertEqual(occurrence["payload"]["date_end_exclusive"], "2026-04-06")

    def test_write_contract_accepts_structured_and_legacy_rules_and_rejects_invalid(self):
        base = {
            "family": str(self.family.id),
            "type": "calendar.event",
            "title": "Regel",
            "starts_at": "2026-01-10T09:00:00+01:00",
            "ends_at": "2026-01-10T10:00:00+01:00",
            "actionable": False,
            "payload": {"provider": "FamilyOS", "recurrence": "weekly"},
        }
        legacy = self.client.post("/api/events/", base, format="json")
        self.assertEqual(legacy.status_code, 201, legacy.data)
        advanced = self.client.post(
            "/api/events/",
            {
                **base,
                "title": "Advanced",
                "payload": {
                    "provider": "FamilyOS",
                    "recurrence": {
                        "frequency": "yearly",
                        "interval": 1,
                        "months": [11],
                        "nth_weekdays": [{"weekday": "TH", "ordinal": -1}],
                    },
                },
            },
            format="json",
        )
        self.assertEqual(advanced.status_code, 201, advanced.data)
        invalid = self.client.post(
            "/api/events/",
            {
                **base,
                "title": "Invalid",
                "payload": {
                    "provider": "FamilyOS",
                    "recurrence": {
                        "frequency": "quarterly",
                        "nth_weekdays": [{"weekday": "XX", "ordinal": 1}],
                    },
                },
            },
            format="json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)
