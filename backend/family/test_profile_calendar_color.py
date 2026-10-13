from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .membership_calendar import CALENDAR_COLOR_PALETTE, get_calendar_color
from .models import Family, Membership


class ProfileCalendarColorTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="profile-color", password="test-pass-123")
        self.family = Family.objects.create(name="Color Family", slug="color-family")
        self.membership = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Taylor",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_profile_exposes_and_updates_membership_calendar_color(self):
        response = self.client.get(f"/api/profile/?family={self.family.id}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(response.data["calendar_color"], CALENDAR_COLOR_PALETTE)
        self.assertEqual(response.data["calendar_color_palette"], list(CALENDAR_COLOR_PALETTE))

        response = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {"family": str(self.family.id), "calendar_color": "#2563EB"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["calendar_color"], "#2563EB")
        self.assertEqual(get_calendar_color(self.membership), "#2563EB")

    def test_profile_rejects_color_outside_palette(self):
        response = self.client.patch(
            f"/api/profile/?family={self.family.id}",
            {"family": str(self.family.id), "calendar_color": "#123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
