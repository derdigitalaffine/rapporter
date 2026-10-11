from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.context_models import ContextLink
from family.models import Family, Membership
from family.travel_models import Trip

from .models import ExpenseLedger


class ExpenseLedgerTripContextTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="expense-owner", password="pw")
        self.guest = User.objects.create_user(username="expense-guest", password="pw")
        self.family = Family.objects.create(name="Alpha", slug="expense-context-alpha")
        self.other_family = Family.objects.create(name="Beta", slug="expense-context-beta")
        Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Owner",
        )
        Membership.objects.create(
            family=self.family,
            user=self.guest,
            role=Membership.Role.GUEST,
            display_name="Guest",
        )
        Membership.objects.create(
            family=self.other_family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Owner Beta",
        )
        self.ledger = ExpenseLedger.objects.create(
            family=self.family,
            name="Sommerurlaub",
            base_currency="EUR",
        )
        self.trip = Trip.objects.create(
            family=self.family,
            title="Italien 2027",
            created_by=self.owner,
        )
        self.other_trip = Trip.objects.create(
            family=self.other_family,
            title="Fremde Reise",
            created_by=self.owner,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def payload(self, *, ledger=None, trip=None):
        return {
            "family": str(self.family.id),
            "source": {
                "type": "expense_ledger",
                "id": str((ledger or self.ledger).id),
            },
            "context": {
                "type": "trip",
                "id": str((trip or self.trip).id),
            },
            "relation": "expense.trip",
        }

    def test_link_is_idempotent_and_visible_from_ledger_anchor(self):
        created = self.client.post("/api/context-links/", self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(created.data["created"])
        self.assertEqual(created.data["link"]["relation"], "expense.trip")
        self.assertEqual(created.data["link"]["source"]["type"], "expense_ledger")
        self.assertEqual(created.data["link"]["source"]["lifecycle"], "available")
        self.assertEqual(created.data["link"]["context"]["type"], "trip")

        repeated = self.client.post("/api/context-links/", self.payload(), format="json")
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertFalse(repeated.data["created"])
        self.assertEqual(repeated.data["link"]["id"], created.data["link"]["id"])
        self.assertEqual(ContextLink.objects.count(), 1)

        listing = self.client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "expense_ledger",
                "anchor_id": str(self.ledger.id),
            },
        )
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["context"]["id"], str(self.trip.id))

    def test_cross_family_trip_fails_closed(self):
        response = self.client.post(
            "/api/context-links/",
            self.payload(trip=self.other_trip),
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(response.data["code"], "context_object_unavailable")
        self.assertFalse(ContextLink.objects.exists())

    def test_guest_can_read_ledger_context_but_cannot_create_link(self):
        guest_client = APIClient()
        guest_client.force_authenticate(self.guest)

        blocked = guest_client.post("/api/context-links/", self.payload(), format="json")
        self.assertEqual(blocked.status_code, 403, blocked.data)
        self.assertEqual(blocked.data["code"], "context_link_forbidden")
        self.assertFalse(ContextLink.objects.exists())

    def test_archived_ledger_keeps_lifecycle_and_existing_link_can_be_removed(self):
        created = self.client.post("/api/context-links/", self.payload(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        link_id = created.data["link"]["id"]

        self.ledger.archived = True
        self.ledger.save(update_fields=["archived", "updated_at"])

        listing = self.client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "expense_ledger",
                "anchor_id": str(self.ledger.id),
            },
        )
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["source"]["lifecycle"], "archived")

        new_link = self.client.post("/api/context-links/", self.payload(), format="json")
        self.assertEqual(new_link.status_code, 403, new_link.data)

        removed = self.client.delete(
            f"/api/context-links/{link_id}/?family={self.family.id}"
        )
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(ContextLink.objects.exists())

    def test_archived_trip_cannot_receive_new_ledger_link(self):
        self.trip.archived = True
        self.trip.stage = Trip.Stage.ARCHIVED
        self.trip.save(update_fields=["archived", "stage", "updated_at"])

        response = self.client.post("/api/context-links/", self.payload(), format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertEqual(response.data["code"], "context_link_forbidden")
        self.assertFalse(ContextLink.objects.exists())
