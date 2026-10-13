from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership


class CalendarEventParticipantsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner_user = User.objects.create_user(username="participant-owner", password="test-pass-123")
        self.first_user = User.objects.create_user(username="participant-first", password="test-pass-123")
        self.second_user = User.objects.create_user(username="participant-second", password="test-pass-123")
        self.outsider_user = User.objects.create_user(username="participant-outsider", password="test-pass-123")
        self.family = Family.objects.create(name="Participants Family", slug="participants-family")
        self.other_family = Family.objects.create(name="Participants Other", slug="participants-other")
        self.owner = Membership.objects.create(family=self.family, user=self.owner_user, role=Membership.Role.OWNER)
        self.first = Membership.objects.create(family=self.family, user=self.first_user, role=Membership.Role.ADULT, display_name="Alex")
        self.second = Membership.objects.create(family=self.family, user=self.second_user, role=Membership.Role.TEEN, display_name="Kim")
        self.outsider = Membership.objects.create(family=self.other_family, user=self.outsider_user, role=Membership.Role.ADULT)
        self.client = APIClient()
        self.client.force_authenticate(self.owner_user)
        self.starts_at = timezone.now() + timedelta(days=1)

    def _event(self, **overrides):
        data = {
            "family": str(self.family.id),
            "type": "calendar.event",
            "title": "Gemeinsamer Termin",
            "starts_at": self.starts_at.isoformat(),
            "ends_at": (self.starts_at + timedelta(hours=1)).isoformat(),
            "actionable": False,
            "payload": {"provider": "FamilyOS"},
        }
        data.update(overrides)
        return data

    def test_create_accepts_multiple_same_family_participants(self):
        response = self.client.post(
            "/api/events/",
            self._event(participants=[str(self.first.id), str(self.second.id)], is_family_event=True),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        event = FamilyEvent.objects.get(pk=response.data["id"])
        self.assertEqual(set(event.participants.values_list("id", flat=True)), {self.first.id, self.second.id})
        self.assertTrue(event.is_family_event)
        self.assertEqual(set(map(str, response.data["participants"])), {str(self.first.id), str(self.second.id)})

    def test_update_can_replace_and_clear_participants(self):
        event = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Termin",
            starts_at=self.starts_at,
            ends_at=self.starts_at + timedelta(hours=1),
        )
        event.participants.add(self.first, self.second)
        response = self.client.patch(
            f"/api/events/{event.id}/",
            {"participants": [str(self.owner.id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(event.participants.values_list("id", flat=True)), [self.owner.id])

        response = self.client.patch(f"/api/events/{event.id}/", {"participants": []}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(event.participants.exists())

    def test_cross_family_participant_is_rejected(self):
        response = self.client.post(
            "/api/events/",
            self._event(participants=[str(self.first.id), str(self.outsider.id)]),
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(FamilyEvent.objects.filter(family=self.family, title="Gemeinsamer Termin").exists())

    def test_people_and_family_marker_are_native_event_only(self):
        response = self.client.post(
            "/api/events/",
            self._event(type="custom.event", participants=[str(self.first.id)]),
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

        response = self.client.post(
            "/api/events/",
            self._event(type="custom.event", is_family_event=True),
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_legacy_member_id_still_syncs_canonical_participants(self):
        response = self.client.post(
            "/api/events/",
            self._event(payload={"provider": "FamilyOS", "member_id": str(self.first.id)}),
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        event = FamilyEvent.objects.get(pk=response.data["id"])
        self.assertEqual(list(event.participants.values_list("id", flat=True)), [self.first.id])

        response = self.client.patch(
            f"/api/events/{event.id}/",
            {"payload": {"provider": "FamilyOS"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(event.participants.exists())
