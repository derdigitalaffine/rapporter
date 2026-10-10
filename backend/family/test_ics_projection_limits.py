from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase

from .ics_projection import sync_ics_projection
from .models import Family, FamilyEvent, IntegrationSource


FIXED_NOW = datetime(2026, 10, 20, 10, 0, tzinfo=dt_timezone.utc)


class IcsProjectionLimitTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(
            name="ICS Limits",
            slug="ics-limits",
            timezone="Europe/Berlin",
        )

    def _source(self, content):
        return IntegrationSource.objects.create(
            family=self.family,
            kind=IntegrationSource.Kind.ICS,
            name="Bounded ICS",
            config={"adapter": "ics", "ics_content": content},
        )

    @patch("family.ics_projection.MAX_ICS_OCCURRENCES_PER_SERIES", 3)
    @patch("family.ics_projection.timezone.now", return_value=FIXED_NOW)
    def test_rejects_series_over_occurrence_limit_before_writing(self, _now):
        source = self._source(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//FamilyOS Test//ICS Limits//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:too-frequent\r\n"
            "DTSTART:20261020T100000Z\r\n"
            "RRULE:FREQ=DAILY;COUNT=6\r\n"
            "SUMMARY:Too frequent\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        existing = FamilyEvent.objects.create(
            family=self.family,
            source=source,
            external_id="last-good",
            type="calendar.event",
            title="Last good snapshot",
            starts_at=FIXED_NOW,
        )

        with self.assertRaisesMessage(ValueError, "zu viele Termine"):
            sync_ics_projection(source)

        self.assertEqual(
            list(FamilyEvent.objects.filter(source=source).values_list("id", flat=True)),
            [existing.id],
        )

    @patch("family.ics_projection.MAX_ICS_PROJECTED_EVENTS", 2)
    @patch("family.ics_projection.timezone.now", return_value=FIXED_NOW)
    def test_rejects_calendar_over_projection_limit_before_writing(self, _now):
        source = self._source(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//FamilyOS Test//ICS Limits//EN\r\n"
            "BEGIN:VEVENT\r\nUID:event-1\r\nDTSTART:20261020T100000Z\r\nSUMMARY:One\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nUID:event-2\r\nDTSTART:20261021T100000Z\r\nSUMMARY:Two\r\nEND:VEVENT\r\n"
            "BEGIN:VEVENT\r\nUID:event-3\r\nDTSTART:20261022T100000Z\r\nSUMMARY:Three\r\nEND:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        existing = FamilyEvent.objects.create(
            family=self.family,
            source=source,
            external_id="last-good",
            type="calendar.event",
            title="Last good snapshot",
            starts_at=FIXED_NOW,
        )

        with self.assertRaisesMessage(ValueError, "zu viele Termine"):
            sync_ics_projection(source)

        self.assertEqual(
            list(FamilyEvent.objects.filter(source=source).values_list("id", flat=True)),
            [existing.id],
        )
