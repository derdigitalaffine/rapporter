from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership
from .waste_calendar import detect_waste_kind, detect_waste_kinds


class WasteCalendarClassificationTests(TestCase):
    def test_detects_common_german_collection_names_and_typo(self):
        cases = {
            "Restmüll": "rest",
            "Restafall Bezirk 3": "rest",
            "Graue Tonne": "rest",
            "Gelbe Tonne": "yellow",
            "Gelber Sack": "yellow",
            "Biomüll / braune Tonne": "bio",
            "Altpapier und Karton": "paper",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(detect_waste_kind(title), expected)

    def test_description_is_used_and_multiple_fractions_are_retained(self):
        self.assertEqual(
            detect_waste_kinds("Abfuhr", "Papier und Gelber Sack"),
            ["paper", "yellow"],
        )

    def test_waste_event_is_classified_automatically_on_save(self):
        family = Family.objects.create(name="Test Family", slug="waste-signal")
        event = FamilyEvent.objects.create(
            family=family,
            type="waste.collection",
            title="Biotonne",
            starts_at=timezone.now() + timedelta(days=1),
            payload={"provider": "Test"},
        )
        event.refresh_from_db()
        self.assertEqual(event.payload["waste_kind"], "bio")
        self.assertEqual(event.payload["waste_kinds"], ["bio"])


class WasteCalendarDashboardTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="owner", password="test-pass-123")
        self.family = Family.objects.create(name="Test Family", slug="waste-dashboard")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_dashboard_guarantees_next_two_waste_events_beyond_normal_window(self):
        now = timezone.now()
        for index in range(12):
            FamilyEvent.objects.create(
                family=self.family,
                type="calendar.event",
                title=f"Termin {index}",
                starts_at=now + timedelta(hours=index + 1),
            )
        waste = []
        for index, title in enumerate(("Restmüll", "Gelbe Tonne", "Papier")):
            waste.append(
                FamilyEvent.objects.create(
                    family=self.family,
                    type="waste.collection",
                    title=title,
                    starts_at=now + timedelta(days=index + 2),
                )
            )

        response = self.client.get(f"/api/dashboard/?family={self.family.id}")
        self.assertEqual(response.status_code, 200, response.data)
        ids = {str(row["id"]) for row in response.data["events"]}
        self.assertIn(str(waste[0].id), ids)
        self.assertIn(str(waste[1].id), ids)
        self.assertNotIn(str(waste[2].id), ids)
