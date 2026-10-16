from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, Routine


class ActionCaptureRouteRegressionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="capture-route-actor")
        self.family = Family.objects.create(name="Capture route", slug="capture-route")
        Membership.objects.create(user=self.user, family=self.family, role="owner")
        self.path = f"/api/actions/capture/?family={self.family.id}"

    def test_get_with_matching_suggestion_uses_raw_django_request_safely(self):
        routine = Routine.objects.create(family=self.family, name="Gepennt")
        client = APIClient()
        client.force_authenticate(self.user)

        response = client.get(f"{self.path}&q=Gepennt")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            any(row["id"] == f"routine:{routine.id}" for row in response.data["suggestions"]),
            response.data,
        )

    def test_post_route_is_csrf_exempt_before_drf_authentication(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_authenticate(self.user)

        response = client.post(
            self.path,
            {
                "title": "Gepennt",
                "create_new": True,
                "request_id": str(uuid4()),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["action_id"].startswith("routine:"), response.data)
