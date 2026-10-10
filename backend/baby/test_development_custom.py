import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership

from .family_modules import set_module
from .pregnancy_service import create_managed_child


User = get_user_model()


class CustomDevelopmentObservationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="development-owner", password="pw")
        self.family = Family.objects.create(name="Development Family", slug="development-family", locale="de", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Alex")
        set_module(self.owner, self.family, enabled=True)
        self.baby = create_managed_child(
            self.owner,
            self.family,
            display_name="Mia",
            birth_date=date.today() - timedelta(days=150),
            gestational_age_weeks=40,
            growth_reference_sex="female",
            client_identity_key=uuid.uuid4(),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_custom_observation_is_returned_by_development_get(self):
        response = self.client.post(
            f"/api/baby/profiles/{self.baby.id}/development/",
            {"title": "Zum ersten Mal gedreht", "state": "observed", "note": "Heute im Wohnzimmer"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        observation_id = response.data["id"]

        reload_response = self.client.get(f"/api/baby/profiles/{self.baby.id}/development/?language=de")
        self.assertEqual(reload_response.status_code, 200, reload_response.data)
        custom = reload_response.data["custom_observations"]
        self.assertEqual(len(custom), 1)
        self.assertEqual(custom[0]["id"], observation_id)
        self.assertEqual(custom[0]["title"], "Zum ersten Mal gedreht")
        self.assertEqual(custom[0]["note"], "Heute im Wohnzimmer")
        self.assertIsNone(custom[0]["media_url"])
