from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership
from .travel_models import Trip


class TravelParticipantTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("travel-participant-owner")
        self.adult = User.objects.create_user("travel-participant-adult")
        self.child = User.objects.create_user("travel-participant-child")
        self.outsider = User.objects.create_user("travel-participant-outsider")
        self.family = Family.objects.create(name="Participants", slug="travel-participants")
        self.other_family = Family.objects.create(name="Other participants", slug="other-travel-participants")
        self.owner_membership = Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Owner",
        )
        self.adult_membership = Membership.objects.create(
            family=self.family,
            user=self.adult,
            role=Membership.Role.ADULT,
            display_name="Adult",
        )
        self.child_membership = Membership.objects.create(
            family=self.family,
            user=self.child,
            role=Membership.Role.CHILD,
            display_name="Child",
        )
        self.outsider_membership = Membership.objects.create(
            family=self.other_family,
            user=self.outsider,
            role=Membership.Role.OWNER,
            display_name="Outsider",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def payload(self, **extra):
        data = {
            "family": str(self.family.id),
            "title": "Family trip",
            "destination": "Berlin",
            "stage": "planning",
            "date_precision": "unknown",
        }
        data.update(extra)
        return data

    def test_create_and_update_trip_participants_with_family_memberships(self):
        created = self.client.post(
            "/api/trips/",
            self.payload(participants=[str(self.owner_membership.id), str(self.child_membership.id)]),
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertCountEqual(
            created.data["participants"],
            [str(self.owner_membership.id), str(self.child_membership.id)],
        )

        trip = Trip.objects.get(pk=created.data["id"])
        self.assertCountEqual(
            trip.participants.values_list("id", flat=True),
            [self.owner_membership.id, self.child_membership.id],
        )

        updated = self.client.patch(
            f"/api/trips/{trip.id}/",
            {"participants": [str(self.adult_membership.id)]},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["participants"], [str(self.adult_membership.id)])
        self.assertEqual(list(trip.participants.values_list("id", flat=True)), [self.adult_membership.id])

    def test_participants_reject_cross_family_memberships_without_mutating_trip(self):
        created = self.client.post(
            "/api/trips/",
            self.payload(participants=[str(self.child_membership.id)]),
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)

        rejected = self.client.patch(
            f"/api/trips/{created.data['id']}/",
            {"participants": [str(self.outsider_membership.id)]},
            format="json",
        )
        self.assertEqual(rejected.status_code, 400, rejected.data)
        self.assertIn("participants", rejected.data)
        trip = Trip.objects.get(pk=created.data["id"])
        self.assertEqual(list(trip.participants.values_list("id", flat=True)), [self.child_membership.id])

    def test_existing_trips_default_to_empty_participants(self):
        created = self.client.post("/api/trips/", self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["participants"], [])
