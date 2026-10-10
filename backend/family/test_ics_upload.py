from datetime import timedelta
from unittest.mock import patch

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


class IcsSubscriptionNameTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="calendar-owner", password="test-pass-123")
        self.family = Family.objects.create(name="Calendar Family", slug="calendar-family")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_catalog_exposes_local_calendar_name_for_ics_subscriptions(self):
        response = self.client.get("/api/integration-hub/catalog/")
        self.assertEqual(response.status_code, 200)
        generic = next(item for item in response.data if item["id"] == "ics")
        name_field = next(field for field in generic["fields"] if field["key"] == "calendar_name")
        self.assertEqual(name_field["type"], "text")
        self.assertEqual(name_field["default"], generic["name"])
        waste = next(item for item in response.data if item["id"] == "waste_kl_city")
        self.assertFalse(any(field["key"] == "calendar_name" for field in waste["fields"]))

    @patch("family.smart_views.sync_with_health", return_value=0)
    def test_connect_uses_clean_local_name_without_storing_it_in_sync_config(self, sync_mock):
        response = self.client.post(
            "/api/integration-hub/connect/",
            {
                "family": str(self.family.id),
                "catalog_id": "ics",
                "values": {
                    "endpoint": "https://example.test/family.ics",
                    "calendar_name": "  Kita   &\n Familie  ",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        source = IntegrationSource.objects.get(family=self.family, config__adapter="ics")
        self.assertEqual(source.name, "Kita & Familie")
        self.assertEqual(source.endpoint, "https://example.test/family.ics")
        self.assertNotIn("calendar_name", source.config)
        self.assertEqual(response.data["source"]["name"], "Kita & Familie")
        sync_mock.assert_called_once_with(source, force=True)

    @patch("family.smart_views.sync_with_health", return_value=0)
    def test_blank_ics_name_falls_back_to_catalog_name(self, _sync_mock):
        response = self.client.post(
            "/api/integration-hub/connect/",
            {
                "family": str(self.family.id),
                "catalog_id": "ics",
                "values": {"endpoint": "https://example.test/family.ics", "calendar_name": "   "},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        source = IntegrationSource.objects.get(family=self.family, config__adapter="ics")
        self.assertEqual(source.name, "Kalender (ICS/iCal)")
