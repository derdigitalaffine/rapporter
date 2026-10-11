from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership
from .models import Expense, ExpenseBudget, get_default_expense_ledger


User = get_user_model()


class FrozenFxTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="fx-owner", password="test")
        self.other = User.objects.create_user(username="fx-adult", password="test")
        self.family = Family.objects.create(name="FX Family", slug="fx-family")
        self.owner = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.adult = Membership.objects.create(
            family=self.family,
            user=self.other,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.ledger = get_default_expense_ledger(self.family)

    def _participants(self):
        return [str(self.owner.id), str(self.adult.id)]

    def _member_fx(self, **overrides):
        payload = {
            "family": str(self.family.id),
            "original_amount": "10.00",
            "original_currency": "usd",
            "fx_rate": "0.9234000000",
            "participants": self._participants(),
            "split_type": "equal",
        }
        payload.update(overrides)
        return payload

    def _shared_fx(self, **overrides):
        payload = {
            "family": str(self.family.id),
            "funding_source": Expense.FundingSource.SHARED,
            "original_amount": "10.00",
            "original_currency": "USD",
            "fx_rate": "0.9000000000",
        }
        payload.update(overrides)
        return payload

    def test_fx_create_freezes_ledger_base_amount_and_currency(self):
        response = self.client.post("/api/expenses/", self._member_fx(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["total_amount"]), Decimal("9.23"))
        self.assertEqual(response.data["currency"], "EUR")
        self.assertEqual(Decimal(response.data["original_amount"]), Decimal("10.00"))
        self.assertEqual(response.data["original_currency"], "USD")
        self.assertEqual(Decimal(response.data["fx_rate"]), Decimal("0.9234000000"))

        expense = Expense.objects.get(id=response.data["id"])
        self.assertEqual(expense.total_amount, Decimal("9.23"))
        self.assertEqual(expense.currency, "EUR")
        self.assertEqual(expense.original_amount, Decimal("10.00"))
        self.assertEqual(expense.original_currency, "USD")
        self.assertEqual(expense.fx_rate, Decimal("0.9234000000"))
        self.assertEqual(sum((row.amount for row in expense.shares.all()), Decimal("0.00")), Decimal("9.23"))

    def test_fx_shared_expense_counts_in_budget_and_supports_allocation(self):
        self.ledger.budget_amount = Decimal("20.00")
        self.ledger.save(update_fields=["budget_amount", "updated_at"])
        budget = ExpenseBudget.objects.create(
            family=self.family,
            ledger=self.ledger,
            name="Reise",
            amount="20.00",
        )

        created = self.client.post("/api/expenses/", self._shared_fx(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(Decimal(created.data["total_amount"]), Decimal("9.00"))
        self.assertEqual(created.data["currency"], "EUR")

        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(Decimal(summary.data["spent_amount"]), Decimal("9.00"))
        self.assertEqual(summary.data["unconverted_expense_count"], 0)

        allocation = self.client.put(
            f"/api/expenses/{created.data['id']}/budget-allocations/",
            {
                "allocations": [
                    {
                        "budget": str(budget.id),
                        "amount_in_budget_currency": "9.00",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(allocation.status_code, 200, allocation.data)
        self.assertEqual(
            Decimal(allocation.data["allocations"][0]["amount_in_budget_currency"]),
            Decimal("9.00"),
        )

    def test_legacy_foreign_currency_remains_compatible_and_unconverted(self):
        created = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "total_amount": "10.00",
                "currency": "USD",
                "participants": self._participants(),
                "split_type": "equal",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["currency"], "USD")
        self.assertEqual(Decimal(created.data["total_amount"]), Decimal("10.00"))
        self.assertIsNone(created.data["original_amount"])
        self.assertIsNone(created.data["original_currency"])
        self.assertIsNone(created.data["fx_rate"])

        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(Decimal(summary.data["spent_amount"]), Decimal("0.00"))
        self.assertEqual(summary.data["unconverted_expense_count"], 1)

    def test_partial_or_conflicting_fx_payload_fails_closed(self):
        partial = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "original_amount": "10.00",
                "original_currency": "USD",
                "participants": self._participants(),
            },
            format="json",
        )
        self.assertEqual(partial.status_code, 400, partial.data)
        self.assertIn("fx", partial.data)

        conflicting_total = self.client.post(
            "/api/expenses/",
            self._member_fx(total_amount="9.99"),
            format="json",
        )
        self.assertEqual(conflicting_total.status_code, 400, conflicting_total.data)
        self.assertIn("total_amount", conflicting_total.data)

        conflicting_currency = self.client.post(
            "/api/expenses/",
            self._member_fx(currency="USD"),
            format="json",
        )
        self.assertEqual(conflicting_currency.status_code, 400, conflicting_currency.data)
        self.assertIn("currency", conflicting_currency.data)

        invalid_rate = self.client.post(
            "/api/expenses/",
            self._member_fx(fx_rate="0"),
            format="json",
        )
        self.assertEqual(invalid_rate.status_code, 400, invalid_rate.data)
        self.assertIn("fx_rate", invalid_rate.data)

    def test_same_currency_requires_unit_rate(self):
        invalid = self.client.post(
            "/api/expenses/",
            self._shared_fx(original_currency="EUR", fx_rate="1.2000000000"),
            format="json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)
        self.assertIn("fx_rate", invalid.data)

        valid = self.client.post(
            "/api/expenses/",
            self._shared_fx(original_currency="EUR", fx_rate="1.0000000000"),
            format="json",
        )
        self.assertEqual(valid.status_code, 201, valid.data)
        self.assertEqual(Decimal(valid.data["total_amount"]), Decimal("10.00"))
        self.assertEqual(valid.data["currency"], "EUR")

    def test_fx_edit_is_explicit_recomputes_base_and_clears_stale_allocation(self):
        budget = ExpenseBudget.objects.create(
            family=self.family,
            ledger=self.ledger,
            name="Aktivitäten",
            amount="30.00",
        )
        created = self.client.post("/api/expenses/", self._shared_fx(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        expense_id = created.data["id"]
        allocation = self.client.put(
            f"/api/expenses/{expense_id}/budget-allocations/",
            {
                "allocations": [
                    {
                        "budget": str(budget.id),
                        "amount_in_budget_currency": "9.00",
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(allocation.status_code, 200, allocation.data)

        unrelated = self.client.patch(
            f"/api/expenses/{expense_id}/",
            {"notes": "Historischer Kurs bleibt eingefroren"},
            format="json",
        )
        self.assertEqual(unrelated.status_code, 200, unrelated.data)
        self.assertEqual(Decimal(unrelated.data["total_amount"]), Decimal("9.00"))
        self.assertEqual(Expense.objects.get(id=expense_id).budget_allocations.count(), 1)

        changed = self.client.patch(
            f"/api/expenses/{expense_id}/",
            {"fx_rate": "0.9500000000"},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(Decimal(changed.data["total_amount"]), Decimal("9.50"))
        expense = Expense.objects.get(id=expense_id)
        self.assertEqual(expense.fx_rate, Decimal("0.9500000000"))
        self.assertEqual(expense.total_amount, Decimal("9.50"))
        self.assertFalse(expense.budget_allocations.exists())

        direct_base_edit = self.client.patch(
            f"/api/expenses/{expense_id}/",
            {"total_amount": "10.00"},
            format="json",
        )
        self.assertEqual(direct_base_edit.status_code, 400, direct_base_edit.data)
        self.assertIn("total_amount", direct_base_edit.data)

    def test_member_fx_edit_requires_explicit_split_confirmation(self):
        created = self.client.post("/api/expenses/", self._member_fx(), format="json")
        self.assertEqual(created.status_code, 201, created.data)
        expense_id = created.data["id"]

        invalid = self.client.patch(
            f"/api/expenses/{expense_id}/",
            {"fx_rate": "1.0000000000"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)
        self.assertIn("participants", invalid.data)

        valid = self.client.patch(
            f"/api/expenses/{expense_id}/",
            {
                "fx_rate": "1.0000000000",
                "participants": self._participants(),
                "split_type": "equal",
            },
            format="json",
        )
        self.assertEqual(valid.status_code, 200, valid.data)
        self.assertEqual(Decimal(valid.data["total_amount"]), Decimal("10.00"))
        expense = Expense.objects.get(id=expense_id)
        self.assertEqual(sum((row.amount for row in expense.shares.all()), Decimal("0.00")), Decimal("10.00"))
