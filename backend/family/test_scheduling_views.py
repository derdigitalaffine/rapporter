from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership


User = get_user_model()


class SchedulingPreviewApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="schedule-ui", password="x")
        self.family = Family.objects.create(
            name="Schedule UI",
            slug="schedule-ui",
            locale="de",
            timezone="Europe/Berlin",
        )
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.ADULT)
        self.other = Family.objects.create(name="Other", slug="schedule-other")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/scheduling/preview/?family={self.family.id}"

    def test_text_is_parsed_server_side_and_returns_summary_and_occurrences(self):
        response = self.client.post(
            self.url,
            {
                "text": "immer am ersten Montag im Quartal",
                "anchor_date": "2026-01-01",
                "language": "de",
                "limit": 3,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["rule"]["recurrence"],
            {"frequency": "quarterly", "interval": 1, "nth_weekdays": [{"weekday": "MO", "ordinal": 1}]},
        )
        self.assertIn("ersten Montag", response.data["summary"])
        self.assertEqual(len(response.data["occurrences"]), 3)
        self.assertEqual(response.data["timezone"], "Europe/Berlin")

    def test_structured_rule_is_normalized_before_preview(self):
        response = self.client.post(
            self.url,
            {
                "rule": {
                    "version": "scheduling-rule-v1",
                    "time_mode": "wall_clock",
                    "anchor_date": "2026-11-01",
                    "recurrence": {
                        "frequency": "yearly",
                        "interval": 1,
                        "months": [11],
                        "nth_weekdays": [{"weekday": "TH", "ordinal": -1}],
                    },
                },
                "language": "de",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rule"]["timezone"], "Europe/Berlin")
        self.assertIn("letzten Donnerstag", response.data["summary"])
        self.assertTrue(response.data["occurrences"])

    def test_family_membership_is_required(self):
        response = self.client.post(
            f"/api/scheduling/preview/?family={self.other.id}",
            {
                "text": "wöchentlich",
                "anchor_date": "2026-01-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_rule_and_text_are_mutually_exclusive(self):
        response = self.client.post(
            self.url,
            {
                "text": "wöchentlich",
                "rule": {"recurrence": {"frequency": "weekly", "interval": 1}},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
