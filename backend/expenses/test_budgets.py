from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership
from .models import (
    Expense,
    ExpenseBudget,
    ExpenseBudgetAllocation,
    ExpenseLedger,
    ExpenseShare,
    get_default_expense_ledger,
)

User = get_user_model()


class ExpenseBudgetCoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="budget-owner", password="test")
        self.sam_user = User.objects.create_user(username="budget-sam", password="test")
        self.foreign_user = User.objects.create_user(username="budget-foreign", password="test")
        self.family = Family.objects.create(name="Budget Familie", slug="budget-familie")
        self.foreign_family = Family.objects.create(name="Fremde Budget Familie", slug="fremde-budget-familie")
        self.owner = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.sam = Membership.objects.create(
            family=self.family,
            user=self.sam_user,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        Membership.objects.create(
            family=self.foreign_family,
            user=self.foreign_user,
            role=Membership.Role.OWNER,
            display_name="Fremd",
        )
        self.ledger = get_default_expense_ledger(self.family)
        self.foreign_ledger = get_default_expense_ledger(self.foreign_family)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _expense(self, amount="10.00", *, ledger=None, currency="EUR"):
        ledger = ledger or self.ledger
        expense = Expense.objects.create(
            family=self.family,
            ledger=ledger,
            title="Budget Test",
            total_amount=Decimal(amount),
            currency=currency,
            paid_by=self.owner,
            created_by=self.user,
        )
        half = (Decimal(amount) / Decimal("2")).quantize(Decimal("0.01"))
        ExpenseShare.objects.create(expense=expense, member=self.owner, amount=half)
        ExpenseShare.objects.create(
            expense=expense,
            member=self.sam,
            amount=Decimal(amount) - half,
        )
        return expense

    def _budget(self, name="Lebensmittel", amount="100.00", *, ledger=None, archived=False):
        ledger = ledger or self.ledger
        return ExpenseBudget.objects.create(
            family=self.family,
            ledger=ledger,
            name=name,
            amount=Decimal(amount),
            archived=archived,
        )

    def _allocation_url(self, expense):
        return f"/api/expenses/{expense.id}/budget-allocations/"

    def test_budget_create_is_ledger_scoped_and_foreign_ledger_is_rejected(self):
        response = self.client.post(
            "/api/expense-budgets/",
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "name": "Freizeit",
                "amount": "80.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        budget = ExpenseBudget.objects.get(id=response.data["id"])
        self.assertEqual(budget.family_id, self.family.id)
        self.assertEqual(budget.ledger_id, self.ledger.id)

        foreign = self.client.post(
            "/api/expense-budgets/",
            {
                "family": str(self.family.id),
                "ledger": str(self.foreign_ledger.id),
                "name": "Nicht erlaubt",
                "amount": "10.00",
            },
            format="json",
        )
        self.assertEqual(foreign.status_code, 400, foreign.data)
        self.assertIn("ledger", foreign.data)

    def test_single_budget_allocation_requires_exact_expense_total(self):
        expense = self._expense("10.00")
        budget = self._budget()
        response = self.client.put(
            self._allocation_url(expense),
            {
                "allocations": [
                    {"budget": str(budget.id), "amount_in_budget_currency": "10.00"},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["allocations"]), 1)
        allocation = ExpenseBudgetAllocation.objects.get(expense=expense)
        self.assertEqual(allocation.amount_in_budget_currency, Decimal("10.00"))

    def test_multi_budget_allocation_is_cent_exact(self):
        expense = self._expense("10.01")
        food = self._budget("Essen")
        leisure = self._budget("Freizeit")
        response = self.client.put(
            self._allocation_url(expense),
            {
                "allocations": [
                    {"budget": str(food.id), "amount_in_budget_currency": "5.00"},
                    {"budget": str(leisure.id), "amount_in_budget_currency": "5.01"},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        total = sum(
            ExpenseBudgetAllocation.objects.filter(expense=expense).values_list(
                "amount_in_budget_currency", flat=True
            ),
            Decimal("0.00"),
        )
        self.assertEqual(total, Decimal("10.01"))

    def test_invalid_replacement_is_atomic_and_preserves_previous_allocation(self):
        expense = self._expense("10.00")
        budget = self._budget()
        valid = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(valid.status_code, 200, valid.data)

        invalid = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "9.99"}]},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)
        allocation = ExpenseBudgetAllocation.objects.get(expense=expense)
        self.assertEqual(allocation.budget_id, budget.id)
        self.assertEqual(allocation.amount_in_budget_currency, Decimal("10.00"))

    def test_cross_ledger_and_archived_budget_ids_fail_closed(self):
        expense = self._expense("10.00")
        other_ledger = ExpenseLedger.objects.create(
            family=self.family,
            name="Reise",
            base_currency="EUR",
        )
        other_budget = self._budget("Reisebudget", ledger=other_ledger)
        archived = self._budget("Alt", archived=True)

        cross_ledger = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(other_budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(cross_ledger.status_code, 400, cross_ledger.data)
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)

        archived_response = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(archived.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(archived_response.status_code, 400, archived_response.data)
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)

    def test_foreign_family_budget_id_is_rejected_without_writing(self):
        expense = self._expense("10.00")
        foreign_budget = ExpenseBudget.objects.create(
            family=self.foreign_family,
            ledger=self.foreign_ledger,
            name="Fremd",
            amount=Decimal("10.00"),
        )
        response = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(foreign_budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)

    def test_soft_overall_budget_reports_overrun_but_never_blocks_expense(self):
        self.ledger.budget_amount = Decimal("5.00")
        self.ledger.save(update_fields=["budget_amount", "updated_at"])
        response = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "title": "Über Budget",
                "total_amount": "12.00",
                "currency": "EUR",
                "participants": [str(self.owner.id), str(self.sam.id)],
                "split_type": "equal",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data["budget_amount"], "5.00")
        self.assertEqual(summary.data["spent_amount"], "12.00")
        self.assertEqual(summary.data["remaining_amount"], "-7.00")
        self.assertTrue(summary.data["over_budget"])

    def test_foreign_currency_is_not_silently_converted(self):
        expense = self._expense("10.00", currency="USD")
        budget = self._budget()
        allocation = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(allocation.status_code, 400, allocation.data)
        self.assertIn("Fremdwährungsumrechnung", str(allocation.data))

        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data["spent_amount"], "0.00")
        self.assertEqual(summary.data["unconverted_expense_count"], 1)

    def test_amount_change_clears_stale_budget_allocations(self):
        expense = self._expense("10.00")
        budget = self._budget()
        response = self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 1)

        expense.total_amount = Decimal("12.00")
        expense.save(update_fields=["total_amount", "updated_at"])
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)

    def test_empty_replacement_clears_budget_allocation(self):
        expense = self._expense("10.00")
        budget = self._budget()
        self.client.put(
            self._allocation_url(expense),
            {"allocations": [{"budget": str(budget.id), "amount_in_budget_currency": "10.00"}]},
            format="json",
        )
        response = self.client.put(
            self._allocation_url(expense),
            {"allocations": []},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["allocations"], [])
        self.assertEqual(ExpenseBudgetAllocation.objects.filter(expense=expense).count(), 0)
