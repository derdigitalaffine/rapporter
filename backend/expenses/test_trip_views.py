from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.context_models import ContextLink
from family.models import Family, Membership
from family.travel_models import Trip

from .models import ExpenseLedger, get_default_expense_ledger


class TripExpenseLedgerViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="trip-ledger-owner", password="pw")
        self.guest = User.objects.create_user(username="trip-ledger-guest", password="pw")
        self.family = Family.objects.create(name="Alpha", slug="trip-ledger-alpha")
        self.other_family = Family.objects.create(name="Beta", slug="trip-ledger-beta")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner")
        Membership.objects.create(family=self.family, user=self.guest, role=Membership.Role.GUEST, display_name="Guest")
        Membership.objects.create(family=self.other_family, user=self.owner, role=Membership.Role.OWNER, display_name="Owner Beta")
        self.trip = Trip.objects.create(family=self.family, title="Japan", created_by=self.owner)
        self.other_trip = Trip.objects.create(family=self.other_family, title="Fremde Reise", created_by=self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def url(self, trip=None):
        row = trip or self.trip
        return f"/api/expense-ledgers/for-trip/?family={self.family.id}&trip={row.id}"

    def test_get_without_link_is_neutral_not_found(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(response.data["code"], "trip_expense_ledger_unavailable")

    def test_post_creates_one_ledger_and_context_link_then_reuses_it(self):
        default = get_default_expense_ledger(self.family)
        created = self.client.post(
            "/api/expense-ledgers/for-trip/",
            {"family": str(self.family.id), "trip": str(self.trip.id)},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["name"], "Japan")
        self.assertEqual(created.data["base_currency"], default.base_currency)
        self.assertFalse(created.data["is_default"])

        ledger_id = created.data["id"]
        self.assertEqual(ExpenseLedger.objects.filter(family=self.family, is_default=False).count(), 1)
        link = ContextLink.objects.get(
            family=self.family,
            relation_key="expense.trip",
            source_type="expense_ledger",
            source_id=ledger_id,
            context_type="trip",
            context_id=self.trip.id,
        )
        self.assertIsNotNone(link)

        repeated = self.client.post(
            "/api/expense-ledgers/for-trip/",
            {"family": str(self.family.id), "trip": str(self.trip.id)},
            format="json",
        )
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(repeated.data["id"], ledger_id)
        self.assertEqual(ExpenseLedger.objects.filter(family=self.family, is_default=False).count(), 1)
        self.assertEqual(ContextLink.objects.filter(relation_key="expense.trip").count(), 1)

        fetched = self.client.get(self.url())
        self.assertEqual(fetched.status_code, 200, fetched.data)
        self.assertEqual(fetched.data["id"], ledger_id)

    def test_cross_family_trip_fails_closed(self):
        response = self.client.post(
            "/api/expense-ledgers/for-trip/",
            {"family": str(self.family.id), "trip": str(self.other_trip.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.data)
        self.assertEqual(response.data["code"], "trip_unavailable")
        self.assertFalse(ContextLink.objects.filter(relation_key="expense.trip").exists())

    def test_trip_and_global_finance_resolve_same_updated_budget_plan(self):
        created = self.client.post(
            "/api/expense-ledgers/for-trip/",
            {"family": str(self.family.id), "trip": str(self.trip.id)},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        ledger_id = created.data["id"]
        updated = self.client.patch(
            f"/api/expense-ledgers/{ledger_id}/",
            {"budget_amount": "4500.00", "estimated_amount": "5200.25", "expected_updated_at": created.data["updated_at"]},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        trip_projection = self.client.get(self.url())
        self.assertEqual(trip_projection.data["id"], ledger_id)
        self.assertEqual(trip_projection.data["estimated_amount"], "5200.25")
        global_projection = self.client.get(f"/api/expense-ledgers/{ledger_id}/budget-summary/")
        self.assertEqual(global_projection.data["budget_amount"], "4500.00")
        self.assertEqual(global_projection.data["estimated_amount"], "5200.25")
        self.assertEqual(global_projection.data["spent_amount"], "0.00")
        self.assertEqual(ExpenseLedger.objects.filter(family=self.family, is_default=False).count(), 1)

    def test_guest_can_read_existing_link_but_cannot_create_one(self):
        created = self.client.post(
            "/api/expense-ledgers/for-trip/",
            {"family": str(self.family.id), "trip": str(self.trip.id)},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)

        guest = APIClient()
        guest.force_authenticate(self.guest)
        fetched = guest.get(self.url())
        self.assertEqual(fetched.status_code, 200, fetched.data)
        self.assertEqual(fetched.data["id"], created.data["id"])

        second_trip = Trip.objects.create(family=self.family, title="Island", created_by=self.owner)
        blocked = guest.post(
            "/api/expense-ledgers/for-trip/",
            {"family": str(self.family.id), "trip": str(second_trip.id)},
            format="json",
        )
        self.assertEqual(blocked.status_code, 403, blocked.data)
        self.assertEqual(blocked.data["code"], "trip_expense_ledger_forbidden")

    def test_archived_linked_ledger_is_not_silently_replaced(self):
        created = self.client.post(
            "/api/expense-ledgers/for-trip/",
            {"family": str(self.family.id), "trip": str(self.trip.id)},
            format="json",
        )
        ledger = ExpenseLedger.objects.get(id=created.data["id"])
        ledger.archived = True
        ledger.save(update_fields=["archived", "updated_at"])

        response = self.client.post(
            "/api/expense-ledgers/for-trip/",
            {"family": str(self.family.id), "trip": str(self.trip.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "trip_expense_ledger_archived")
        self.assertEqual(ExpenseLedger.objects.filter(family=self.family, is_default=False).count(), 1)
