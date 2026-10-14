from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .calendar_planner_models import CalendarPlannerPreference
from .models import Family, Membership


class CalendarPlannerPreferenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="planner-owner", password="test-pass-123")
        self.member = User.objects.create_user(username="planner-member", password="test-pass-123")
        self.outsider = User.objects.create_user(username="planner-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Planner Family", slug="planner-family")
        self.other_family = Family.objects.create(name="Other Family", slug="planner-other")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Alex")
        self.member_membership = Membership.objects.create(family=self.family, user=self.member, role=Membership.Role.ADULT, display_name="Sam")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    @property
    def url(self):
        return f"/api/calendar-planner-preferences/?family={self.family.id}"

    def test_lane_order_is_stored_per_user_and_family(self):
        initial = self.client.get(self.url)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.data["lane_order"], [])

        requested = [
            str(self.member_membership.id),
            "__ics__",
            "unknown-lane",
            str(self.owner_membership.id),
            "__family__",
            str(self.member_membership.id),
        ]
        saved = self.client.patch(
            self.url,
            {"family": str(self.family.id), "lane_order": requested},
            format="json",
        )
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(
            saved.data["lane_order"],
            [str(self.member_membership.id), "__ics__", str(self.owner_membership.id), "__family__"],
        )
        preference = CalendarPlannerPreference.objects.get(user=self.owner, family=self.family)
        self.assertEqual(preference.lane_order, saved.data["lane_order"])

        other_client = APIClient()
        other_client.force_authenticate(self.member)
        other = other_client.get(self.url)
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.data["lane_order"], [])

    def test_non_member_cannot_read_or_write_family_preferences(self):
        outsider = APIClient()
        outsider.force_authenticate(self.outsider)
        url = f"/api/calendar-planner-preferences/?family={self.family.id}"
        self.assertEqual(outsider.get(url).status_code, 403)
        self.assertEqual(
            outsider.patch(url, {"family": str(self.family.id), "lane_order": ["__family__"]}, format="json").status_code,
            403,
        )

    def test_invalid_lane_order_is_rejected(self):
        response = self.client.patch(
            self.url,
            {"family": str(self.family.id), "lane_order": "not-a-list"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CalendarPlannerPreference.objects.filter(user=self.owner, family=self.family).exists())

    def test_preferences_are_isolated_by_family(self):
        Membership.objects.create(family=self.other_family, user=self.owner, role=Membership.Role.OWNER)
        self.client.patch(
            self.url,
            {"family": str(self.family.id), "lane_order": ["__ics__", "__family__"]},
            format="json",
        )
        other = self.client.get(f"/api/calendar-planner-preferences/?family={self.other_family.id}")
        self.assertEqual(other.status_code, 200)
        self.assertEqual(other.data["lane_order"], [])
