from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family, FamilyEvent, Membership

from .models import Decision


class DecisionCalendarContextTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="decision-calendar-owner")
        self.family = Family.objects.create(name="Decision Calendar", slug="decision-calendar")
        Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_weather_projection_is_not_addressable_as_decision_event_context(self):
        weather = FamilyEvent.objects.create(
            family=self.family,
            type="weather.current",
            title="Weather observation",
            starts_at=timezone.now(),
        )

        response = self.client.post(
            "/api/decisions/",
            {
                "family": str(self.family.id),
                "question": "Should weather data become an appointment poll?",
                "options": ["No", "Still no"],
                "context": {"type": "event", "id": str(weather.id)},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404, response.data)
        self.assertFalse(Decision.objects.exists())
