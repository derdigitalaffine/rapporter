from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .ics_projection import sync_ics_projection
from .models import Family, FamilyEvent, IntegrationSource, Membership


class CalendarV2ProjectionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="calendar-v2-owner", password="test-pass-123")
        self.family = Family.objects.create(name="Calendar V2", slug="calendar-v2", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _ics(self):
        start = (timezone.now().astimezone(dt_timezone.utc) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
        second = start + timedelta(days=1)
        third = start + timedelta(days=2)
        all_day = timezone.localdate() + timedelta(days=1)
        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//FamilyOS Test//Calendar V2//EN\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:recurring-1\r\n"
            f"DTSTART:{start:%Y%m%dT%H%M%SZ}\r\n"
            f"DTEND:{(start + timedelta(hours=1)):%Y%m%dT%H%M%SZ}\r\n"
            "RRULE:FREQ=DAILY;COUNT=3\r\n"
            f"EXDATE:{second:%Y%m%dT%H%M%SZ}\r\n"
            "SUMMARY:Training\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:recurring-1\r\n"
            f"RECURRENCE-ID:{third:%Y%m%dT%H%M%SZ}\r\n"
            f"DTSTART:{(third + timedelta(hours=6)):%Y%m%dT%H%M%SZ}\r\n"
            f"DTEND:{(third + timedelta(hours=7)):%Y%m%dT%H%M%SZ}\r\n"
            "SUMMARY:Training verschoben\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:all-day-1\r\n"
            f"DTSTART;VALUE=DATE:{all_day:%Y%m%d}\r\n"
            f"DTEND;VALUE=DATE:{(all_day + timedelta(days=1)):%Y%m%d}\r\n"
            "SUMMARY:Ganztag\r\n"
            "END:VEVENT\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:cancelled-1\r\n"
            f"DTSTART:{start:%Y%m%dT%H%M%SZ}\r\n"
            "STATUS:CANCELLED\r\n"
            "SUMMARY:Abgesagt\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

    def test_materializes_recurrence_exdates_exception_and_all_day(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            kind=IntegrationSource.Kind.CALENDAR,
            name="Kita & Familie",
            config={"adapter": "ics", "ics_content": self._ics()},
        )
        count = sync_ics_projection(source)
        self.assertEqual(count, 3)
        rows = list(FamilyEvent.objects.filter(source=source).order_by("starts_at"))
        self.assertEqual(len(rows), 3)
        self.assertFalse(any(row.title == "Abgesagt" for row in rows))
        moved = next(row for row in rows if row.title == "Training verschoben")
        self.assertTrue(moved.payload["recurring"])
        self.assertIn("recurrence_id", moved.payload)
        all_day = next(row for row in rows if row.title == "Ganztag")
        self.assertTrue(all_day.payload["all_day"])
        self.assertEqual(all_day.payload["date_start"], (timezone.localdate() + timedelta(days=1)).isoformat())
        self.assertEqual(all_day.payload["provider"], "Kita & Familie")

    def test_successful_resync_removes_stale_projection(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            kind=IntegrationSource.Kind.CALENDAR,
            name="ICS",
            config={"adapter": "ics", "ics_content": self._ics()},
        )
        sync_ics_projection(source)
        self.assertTrue(FamilyEvent.objects.filter(source=source, external_id__startswith="recurring-1").exists())
        day = timezone.localdate() + timedelta(days=5)
        source.config = {
            "adapter": "ics",
            "ics_content": (
                "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//FamilyOS//Test//EN\r\n"
                "BEGIN:VEVENT\r\nUID:new-only\r\n"
                f"DTSTART;VALUE=DATE:{day:%Y%m%d}\r\n"
                "SUMMARY:Neu\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
            ),
        }
        source.save(update_fields=["config", "updated_at"])
        self.assertEqual(sync_ics_projection(source), 1)
        self.assertFalse(FamilyEvent.objects.filter(source=source, external_id__startswith="recurring-1").exists())
        self.assertEqual(list(FamilyEvent.objects.filter(source=source).values_list("external_id", flat=True)), ["new-only"])

    def test_source_appearance_preserves_sync_config(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            kind=IntegrationSource.Kind.CALENDAR,
            name="Privat",
            config={"adapter": "ics", "ics_content": "secret-calendar-payload"},
        )
        response = self.client.patch(
            f"/api/calendar-sources/{source.id}/appearance/",
            {"color": "purple", "icon": "heart"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        source.refresh_from_db()
        self.assertEqual(source.config["ics_content"], "secret-calendar-payload")
        self.assertEqual(source.config["appearance"], {"color": "purple", "icon": "heart"})
        self.assertNotEqual(response.data["config"]["ics_content"], "secret-calendar-payload")

    def test_source_appearance_rejects_arbitrary_font_awesome_name(self):
        source = IntegrationSource.objects.create(family=self.family, kind=IntegrationSource.Kind.CALENDAR, name="Privat", config={"adapter": "ics"})
        response = self.client.patch(
            f"/api/calendar-sources/{source.id}/appearance/",
            {"color": "purple", "icon": "fa-skull-crossbones"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_source_backed_events_are_read_only_through_event_api(self):
        source = IntegrationSource.objects.create(family=self.family, kind=IntegrationSource.Kind.CALENDAR, name="Extern", config={"adapter": "ics"})
        event = FamilyEvent.objects.create(
            family=self.family,
            source=source,
            external_id="external-1",
            type="calendar.event",
            title="Extern",
            starts_at=timezone.now() + timedelta(days=1),
            payload={"provider": "Extern"},
        )
        patch_response = self.client.patch(f"/api/events/{event.id}/", {"title": "Manipuliert"}, format="json")
        delete_response = self.client.delete(f"/api/events/{event.id}/")
        self.assertEqual(patch_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)
        event.refresh_from_db()
        self.assertEqual(event.title, "Extern")
