from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, IntegrationSource, Membership


class WasteCalendarUploadTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="owner", password="test-pass-123")
        self.family = Family.objects.create(name="Test Family", slug="test-family")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def calendar_bytes(self):
        tomorrow = timezone.localdate() + timedelta(days=1)
        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Kaiserslautern Test//Waste//DE\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:waste-upload-1\r\n"
            f"DTSTART;VALUE=DATE:{tomorrow:%Y%m%d}\r\n"
            "SUMMARY:Restmüll\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        ).encode("utf-8")

    def test_city_waste_calendar_accepts_downloaded_ics_file(self):
        upload = SimpleUploadedFile("abfallkalender.ics", self.calendar_bytes(), content_type="text/calendar")
        response = self.client.post(
            "/api/integration-hub/connect/",
            {
                "family": str(self.family.id),
                "catalog_id": "waste_kl_city",
                "values": "{}",
                "ics_file": upload,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["synced"], 1)
        source = IntegrationSource.objects.get(family=self.family, config__adapter="waste_kl_city")
        self.assertEqual(source.endpoint, "")
        self.assertEqual(source.config["ics_filename"], "abfallkalender.ics")
        self.assertIn("BEGIN:VCALENDAR", source.config["ics_content"])
        self.assertEqual(response.data["source"]["config"]["ics_content"], "••••••••")
        self.assertTrue(
            FamilyEvent.objects.filter(
                family=self.family,
                source=source,
                type="waste.collection",
                title="Restmüll",
            ).exists()
        )

    def test_city_waste_calendar_rejects_non_ics_extension(self):
        upload = SimpleUploadedFile("abfallkalender.txt", self.calendar_bytes(), content_type="text/plain")
        response = self.client.post(
            "/api/integration-hub/connect/",
            {"family": str(self.family.id), "catalog_id": "waste_kl_city", "values": "{}", "ics_file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(".ics", response.data["detail"])
        self.assertFalse(IntegrationSource.objects.filter(family=self.family, config__adapter="waste_kl_city").exists())

    def test_city_waste_calendar_rejects_invalid_ics(self):
        upload = SimpleUploadedFile("abfallkalender.ics", b"not a calendar", content_type="text/calendar")
        response = self.client.post(
            "/api/integration-hub/connect/",
            {"family": str(self.family.id), "catalog_id": "waste_kl_city", "values": "{}", "ics_file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ICS", response.data["detail"])
        self.assertFalse(IntegrationSource.objects.filter(family=self.family, config__adapter="waste_kl_city").exists())
