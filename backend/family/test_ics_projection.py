from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .ics_projection import sync_ics_projection
from .integration_health import sync_with_health
from .models import Family, FamilyEvent, IntegrationSource, Membership


FIXED_NOW = datetime(2026, 10, 20, 10, 0, tzinfo=dt_timezone.utc)


class IcsProjectionTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(
            name="ICS Projection",
            slug="ics-projection",
            timezone="Europe/Berlin",
        )

    def _source(self, content, *, name="Kita & Familie"):
        return IntegrationSource.objects.create(
            family=self.family,
            kind=IntegrationSource.Kind.ICS,
            name=name,
            config={"adapter": "ics", "ics_content": content},
        )

    def _recurring_ics(self):
        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//FamilyOS Test//ICS Projection//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:recurring-1\r\n"
            "DTSTART:20261021T090000Z\r\n"
            "DTEND:20261021T100000Z\r\n"
            "RRULE:FREQ=DAILY;COUNT=4\r\n"
            "EXDATE:20261022T090000Z\r\n"
            "RDATE:20261025T090000Z\r\n"
            "SUMMARY:Training\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:recurring-1\r\n"
            "RECURRENCE-ID:20261023T090000Z\r\n"
            "DTSTART:20261023T150000Z\r\n"
            "DTEND:20261023T163000Z\r\n"
            "SUMMARY:Training verschoben\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:recurring-1\r\n"
            "RECURRENCE-ID:20261024T090000Z\r\n"
            "DTSTART:20261024T090000Z\r\n"
            "STATUS:CANCELLED\r\n"
            "SUMMARY:Abgesagte Serie\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:all-day-1\r\n"
            "DTSTART;VALUE=DATE:20261025\r\n"
            "DTEND;VALUE=DATE:20261026\r\n"
            "SUMMARY:Ganztag\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:cancelled-1\r\n"
            "DTSTART:20261021T120000Z\r\n"
            "STATUS:CANCELLED\r\n"
            "SUMMARY:Abgesagt\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

    @patch("family.ics_projection.timezone.now", return_value=FIXED_NOW)
    def test_materializes_rrule_rdate_exdate_exception_cancelled_and_all_day(self, _now):
        source = self._source(self._recurring_ics())

        count = sync_ics_projection(source)

        self.assertEqual(count, 4)
        rows = list(FamilyEvent.objects.filter(source=source).order_by("starts_at"))
        self.assertEqual(len(rows), 4)
        self.assertFalse(any(row.title.startswith("Abgesagt") for row in rows))

        recurring = [row for row in rows if row.external_id.startswith("recurring-1::")]
        self.assertEqual(len(recurring), 3)
        self.assertEqual(
            {row.starts_at.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%MZ") for row in recurring},
            {"2026-10-21T09:00Z", "2026-10-23T15:00Z", "2026-10-25T09:00Z"},
        )
        moved = next(row for row in recurring if row.title == "Training verschoben")
        self.assertEqual(
            moved.ends_at.astimezone(dt_timezone.utc) - moved.starts_at.astimezone(dt_timezone.utc),
            timedelta(minutes=90),
        )
        self.assertTrue(moved.payload["recurring"])
        self.assertEqual(
            moved.payload["recurrence_id"],
            "2026-10-23T09:00:00+00:00",
        )

        all_day = next(row for row in rows if row.external_id == "all-day-1")
        self.assertTrue(all_day.payload["all_day"])
        self.assertEqual(all_day.payload["date_start"], "2026-10-25")
        self.assertEqual(all_day.payload["date_end_exclusive"], "2026-10-26")
        self.assertEqual(all_day.payload["provider"], "Kita & Familie")

    @patch("family.ics_projection.timezone.now", return_value=FIXED_NOW)
    def test_resync_keeps_occurrence_identity_and_removes_stale_rows(self, _now):
        source = self._source(self._recurring_ics())
        sync_ics_projection(source)
        first_ids = {
            row.external_id: row.id
            for row in FamilyEvent.objects.filter(source=source)
        }

        self.assertEqual(sync_ics_projection(source), 4)
        second_ids = {
            row.external_id: row.id
            for row in FamilyEvent.objects.filter(source=source)
        }
        self.assertEqual(second_ids, first_ids)

        source.config = {
            "adapter": "ics",
            "ics_content": (
                "BEGIN:VCALENDAR\r\n"
                "VERSION:2.0\r\n"
                "PRODID:-//FamilyOS Test//ICS Projection//EN\r\n"
                "BEGIN:VEVENT\r\n"
                "UID:new-only\r\n"
                "DTSTART;VALUE=DATE:20261026\r\n"
                "SUMMARY:Neu\r\n"
                "END:VEVENT\r\n"
                "END:VCALENDAR\r\n"
            ),
        }
        source.save(update_fields=["config", "updated_at"])

        self.assertEqual(sync_ics_projection(source), 1)
        self.assertEqual(
            list(
                FamilyEvent.objects.filter(source=source).values_list(
                    "external_id",
                    flat=True,
                )
            ),
            ["new-only"],
        )

    @patch("family.ics_projection.timezone.now", return_value=FIXED_NOW)
    def test_date_until_and_floating_until_expand_in_family_civil_time(self, _now):
        source = self._source(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//FamilyOS Test//ICS Projection//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:all-day-series\r\n"
            "DTSTART;VALUE=DATE:20261024\r\n"
            "RRULE:FREQ=DAILY;UNTIL=20261026\r\n"
            "SUMMARY:All-day series\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:floating-series\r\n"
            "DTSTART:20261024T090000\r\n"
            "DTEND:20261024T100000\r\n"
            "RRULE:FREQ=DAILY;UNTIL=20261026T090000\r\n"
            "SUMMARY:Floating series\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        self.assertEqual(sync_ics_projection(source), 6)

        all_day = list(
            FamilyEvent.objects.filter(
                source=source,
                external_id__startswith="all-day-series::",
            ).order_by("starts_at")
        )
        self.assertEqual(
            [row.payload["date_start"] for row in all_day],
            ["2026-10-24", "2026-10-25", "2026-10-26"],
        )

        berlin = ZoneInfo(self.family.timezone)
        floating = list(
            FamilyEvent.objects.filter(
                source=source,
                external_id__startswith="floating-series::",
            ).order_by("starts_at")
        )
        self.assertEqual(len(floating), 3)
        self.assertEqual(
            [
                row.starts_at.astimezone(berlin).strftime("%Y-%m-%d %H:%M %z")
                for row in floating
            ],
            [
                "2026-10-24 09:00 +0200",
                "2026-10-25 09:00 +0100",
                "2026-10-26 09:00 +0100",
            ],
        )

    @patch("family.ics_projection.timezone.now", return_value=FIXED_NOW)
    def test_resync_collapses_preexisting_duplicate_projection_rows(self, _now):
        source = self._source(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//FamilyOS Test//ICS Projection//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:single-1\r\n"
            "DTSTART:20261021T090000Z\r\n"
            "SUMMARY:Single\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )
        for title in ("Duplicate A", "Duplicate B"):
            FamilyEvent.objects.create(
                family=self.family,
                source=source,
                external_id="single-1",
                type="calendar.event",
                title=title,
                starts_at=FIXED_NOW,
            )

        self.assertEqual(sync_ics_projection(source), 1)
        rows = FamilyEvent.objects.filter(source=source, external_id="single-1")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().title, "Single")

    @patch("family.ics_projection.timezone.now", return_value=FIXED_NOW)
    def test_invalid_rrule_does_not_destroy_last_successful_projection(self, _now):
        source = self._source(
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//FamilyOS Test//ICS Projection//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:broken-1\r\n"
            "DTSTART:20261021T090000Z\r\n"
            "RRULE:FREQ=NOT-A-FREQUENCY\r\n"
            "SUMMARY:Broken\r\n"
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

        with self.assertRaisesMessage(ValueError, "Wiederholungsregel"):
            sync_ics_projection(source)

        self.assertTrue(FamilyEvent.objects.filter(pk=existing.pk).exists())
        self.assertFalse(
            FamilyEvent.objects.filter(source=source, external_id="broken-1").exists()
        )

    @patch("family.ics_projection.timezone.now", return_value=FIXED_NOW)
    def test_health_sync_uses_projection_for_generic_ics(self, _now):
        source = self._source(self._recurring_ics())

        self.assertEqual(sync_with_health(source, force=True), 4)

        source.refresh_from_db()
        self.assertEqual(source.last_sync_status, "success")
        self.assertEqual(FamilyEvent.objects.filter(source=source).count(), 4)


class ExternalCalendarReadOnlyTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="calendar-owner",
            password="test-pass-123",
        )
        self.family = Family.objects.create(
            name="Calendar Family",
            slug="calendar-readonly",
        )
        Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
        )
        self.source = IntegrationSource.objects.create(
            family=self.family,
            kind=IntegrationSource.Kind.ICS,
            name="Extern",
            config={"adapter": "ics"},
        )
        self.event = FamilyEvent.objects.create(
            family=self.family,
            source=self.source,
            external_id="external-1",
            type="calendar.event",
            title="Extern",
            starts_at=timezone.now() + timedelta(days=1),
            payload={"provider": "Extern"},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_source_backed_events_cannot_be_created_updated_or_deleted(self):
        create_response = self.client.post(
            "/api/events/",
            {
                "family": str(self.family.id),
                "source": str(self.source.id),
                "type": "calendar.event",
                "title": "Forged external",
                "starts_at": (timezone.now() + timedelta(days=2)).isoformat(),
            },
            format="json",
        )
        patch_response = self.client.patch(
            f"/api/events/{self.event.id}/",
            {"title": "Manipuliert", "source": None},
            format="json",
        )
        delete_response = self.client.delete(f"/api/events/{self.event.id}/")

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(patch_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "Extern")
        self.assertEqual(self.event.source_id, self.source.id)

    def test_source_backed_event_in_other_family_is_not_addressable(self):
        User = get_user_model()
        other_user = User.objects.create_user(
            username="other-calendar-owner",
            password="test-pass-123",
        )
        other_family = Family.objects.create(
            name="Other Family",
            slug="other-calendar-family",
        )
        Membership.objects.create(
            family=other_family,
            user=other_user,
            role=Membership.Role.OWNER,
        )
        other_source = IntegrationSource.objects.create(
            family=other_family,
            kind=IntegrationSource.Kind.ICS,
            name="Other external",
            config={"adapter": "ics"},
        )
        other_event = FamilyEvent.objects.create(
            family=other_family,
            source=other_source,
            external_id="other-external",
            type="calendar.event",
            title="Other external",
            starts_at=timezone.now() + timedelta(days=1),
        )

        patch_response = self.client.patch(
            f"/api/events/{other_event.id}/",
            {"title": "Nope"},
            format="json",
        )
        delete_response = self.client.delete(f"/api/events/{other_event.id}/")

        self.assertEqual(patch_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)

    def test_manual_event_remains_editable(self):
        event = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Manuell",
            starts_at=timezone.now() + timedelta(days=1),
        )

        response = self.client.patch(
            f"/api/events/{event.id}/",
            {"title": "Manuell geändert"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        event.refresh_from_db()
        self.assertEqual(event.title, "Manuell geändert")
