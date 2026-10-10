from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership


class CalendarWindowTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="calendar-window-owner")
        self.family = Family.objects.create(name="Calendar Window", slug="calendar-window", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=user, role="owner")
        self.client = APIClient()
        self.client.force_authenticate(user)
        self.zone = ZoneInfo("Europe/Berlin")

    def rows(self, response):
        return response.data.get("results", response.data)

    def event(self, title, start, end=None, **kwargs):
        return FamilyEvent.objects.create(
            family=self.family,
            type=kwargs.pop("type", "calendar.event"),
            title=title,
            starts_at=start,
            ends_at=end,
            payload=kwargs.pop("payload", {}),
            **kwargs,
        )

    def test_bounded_window_is_not_hidden_by_first_page_of_history(self):
        historical = datetime(2024, 1, 1, 9, tzinfo=self.zone)
        for index in range(101):
            start = historical + timedelta(hours=index)
            self.event(f"old-{index}", start, start + timedelta(minutes=30))
        current = self.event(
            "Visible appointment",
            datetime(2026, 10, 12, 15, tzinfo=self.zone),
            datetime(2026, 10, 12, 16, tzinfo=self.zone),
        )
        crossing = self.event(
            "Cross-midnight",
            datetime(2026, 10, 10, 23, tzinfo=self.zone),
            datetime(2026, 10, 11, 1, tzinfo=self.zone),
        )
        self.event(
            "Outside window",
            datetime(2026, 11, 1, 9, tzinfo=self.zone),
            datetime(2026, 11, 1, 10, tzinfo=self.zone),
        )

        response = self.client.get(
            "/api/events/",
            {
                "family": str(self.family.id),
                "start": "2026-10-11",
                "end": "2026-10-17",
                "birthdays": "0",
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        ids = {str(row["id"]) for row in self.rows(response)}
        self.assertEqual(ids, {str(current.id), str(crossing.id)})

    def test_window_is_family_isolated_and_can_include_undated_rows(self):
        undated = self.event("Undated", None)
        other_user = get_user_model().objects.create_user(username="calendar-window-other")
        other_family = Family.objects.create(name="Other", slug="calendar-window-other", timezone="Europe/Berlin")
        Membership.objects.create(family=other_family, user=other_user, role="owner")
        FamilyEvent.objects.create(
            family=other_family,
            type="calendar.event",
            title="Secret",
            starts_at=datetime(2026, 10, 12, 12, tzinfo=self.zone),
        )

        response = self.client.get(
            "/api/events/",
            {
                "family": str(self.family.id),
                "start": "2026-10-11",
                "end": "2026-10-17",
                "include_undated": "1",
                "birthdays": "0",
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        rows = self.rows(response)
        self.assertEqual([row["title"] for row in rows], ["Undated"])
        self.assertEqual(str(rows[0]["id"]), str(undated.id))

    def test_range_caps_two_years_and_single_bound_keeps_legacy_read(self):
        single_bound = self.client.get(
            "/api/events/",
            {"family": str(self.family.id), "start": "2026-10-11", "birthdays": "0"},
        )
        too_large = self.client.get(
            "/api/events/",
            {"family": str(self.family.id), "start": "2024-01-01", "end": "2027-01-03"},
        )
        self.assertEqual(single_bound.status_code, 200)
        self.assertEqual(too_large.status_code, 400)
