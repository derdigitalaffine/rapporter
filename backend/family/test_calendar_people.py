from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership


class CalendarEventMemberAssignmentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="calendar-owner", password="test-pass-123")
        self.member_user = User.objects.create_user(username="calendar-member", password="test-pass-123")
        self.outsider_user = User.objects.create_user(username="calendar-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Marker Family", slug="marker-family")
        self.other_family = Family.objects.create(name="Other Family", slug="other-marker-family")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        self.member = Membership.objects.create(
            family=self.family,
            user=self.member_user,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        self.outsider = Membership.objects.create(
            family=self.other_family,
            user=self.outsider_user,
            role=Membership.Role.ADULT,
            display_name="Outside",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.starts_at = timezone.now() + timedelta(days=1)

    def _payload(self, member_id=None):
        payload = {"provider": "FamilyOS", "location": "Küche", "description": ""}
        if member_id is not None:
            payload["member_id"] = str(member_id)
        return payload

    def test_create_and_update_accept_same_family_membership_and_can_clear_it(self):
        response = self.client.post(
            "/api/events/",
            {
                "family": str(self.family.id),
                "type": "calendar.event",
                "title": "Familientermin",
                "starts_at": self.starts_at.isoformat(),
                "ends_at": (self.starts_at + timedelta(hours=1)).isoformat(),
                "actionable": False,
                "payload": self._payload(self.member.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        event = FamilyEvent.objects.get(pk=response.data["id"])
        self.assertEqual(event.payload["member_id"], str(self.member.id))

        response = self.client.patch(
            f"/api/events/{event.id}/",
            {"payload": self._payload()},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        event.refresh_from_db()
        self.assertNotIn("member_id", event.payload)

    def test_cross_family_membership_is_rejected_without_creating_event(self):
        response = self.client.post(
            "/api/events/",
            {
                "family": str(self.family.id),
                "type": "calendar.event",
                "title": "Fremde Person",
                "starts_at": self.starts_at.isoformat(),
                "ends_at": (self.starts_at + timedelta(hours=1)).isoformat(),
                "actionable": False,
                "payload": self._payload(self.outsider.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(FamilyEvent.objects.filter(family=self.family, title="Fremde Person").count(), 0)

    def test_member_marker_is_only_allowed_for_native_calendar_event_type(self):
        response = self.client.post(
            "/api/events/",
            {
                "family": str(self.family.id),
                "type": "custom.event",
                "title": "Nicht nativ",
                "starts_at": self.starts_at.isoformat(),
                "ends_at": (self.starts_at + timedelta(hours=1)).isoformat(),
                "actionable": False,
                "payload": self._payload(self.member.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
