from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase

from .ics_projection import sync_ics_projection
from .models import Family, FamilyEvent, IntegrationSource


FIXED_NOW = datetime(2026, 10, 20, 10, 0, tzinfo=dt_timezone.utc)
SINGLE_ICS = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//FamilyOS Test//Legacy Cleanup//EN\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:single-1\r\n"
    "DTSTART:20261021T090000Z\r\n"
    "DTEND:20261021T100000Z\r\n"
    "SUMMARY:Benannter Kalendertermin\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


class IntegrationProjectionCleanupTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(
            name="Legacy ICS Cleanup",
            slug="legacy-ics-cleanup",
            timezone="Europe/Berlin",
        )
        self.source = IntegrationSource.objects.create(
            family=self.family,
            kind=IntegrationSource.Kind.ICS,
            name="Familienkalender",
            config={"adapter": "ics", "ics_content": SINGLE_ICS},
        )

    @patch("family.ics_projection.timezone.now", return_value=FIXED_NOW)
    def test_sync_removes_matching_source_less_legacy_duplicates_only(self, _now):
        legacy_ids = []
        for index in range(3):
            legacy_ids.append(
                FamilyEvent.objects.create(
                    family=self.family,
                    external_id="single-1",
                    type="calendar.event",
                    title=f"Legacy FamilyOS {index + 1}",
                    starts_at=FIXED_NOW,
                    payload={"provider": "ICS/iCal"},
                ).id
            )
        manual = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Manuell",
            starts_at=FIXED_NOW,
        )
        same_external_other_type = FamilyEvent.objects.create(
            family=self.family,
            external_id="single-1",
            type="travel.event",
            title="Andere Domain",
            starts_at=FIXED_NOW,
        )
        unrelated_external = FamilyEvent.objects.create(
            family=self.family,
            external_id="other-1",
            type="calendar.event",
            title="Andere externe Altlast",
            starts_at=FIXED_NOW,
        )

        self.assertEqual(sync_ics_projection(self.source), 1)

        self.assertFalse(FamilyEvent.objects.filter(id__in=legacy_ids).exists())
        active = FamilyEvent.objects.get(source=self.source, external_id="single-1")
        self.assertEqual(active.title, "Benannter Kalendertermin")
        self.assertTrue(FamilyEvent.objects.filter(pk=manual.pk).exists())
        self.assertTrue(FamilyEvent.objects.filter(pk=same_external_other_type.pk).exists())
        self.assertTrue(FamilyEvent.objects.filter(pk=unrelated_external.pk).exists())

        self.assertEqual(sync_ics_projection(self.source), 1)
        self.assertEqual(
            FamilyEvent.objects.filter(source=self.source, external_id="single-1").count(),
            1,
        )
        self.assertTrue(FamilyEvent.objects.filter(pk=manual.pk).exists())

    def test_deleting_integration_source_deletes_projected_events_without_touching_manual(self):
        projected = FamilyEvent.objects.create(
            family=self.family,
            source=self.source,
            external_id="external-1",
            type="calendar.event",
            title="Extern",
            starts_at=FIXED_NOW,
        )
        manual = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Manuell",
            starts_at=FIXED_NOW,
        )

        self.source.delete()

        self.assertFalse(FamilyEvent.objects.filter(pk=projected.pk).exists())
        self.assertTrue(FamilyEvent.objects.filter(pk=manual.pk).exists())
        self.assertFalse(
            FamilyEvent.objects.filter(
                family=self.family,
                source__isnull=True,
                external_id="external-1",
            ).exists()
        )
