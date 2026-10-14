from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership, ShoppingItem, ShoppingList
from .commitment_models import BudgetCommitment
from .models import Expense, ExpenseBudget, ExpenseShare, get_default_expense_ledger

User = get_user_model()


class BudgetCommitmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="commitment-owner", password="test")
        self.other = User.objects.create_user(username="commitment-other", password="test")
        self.family = Family.objects.create(name="Commitment Familie", slug="commitment-family")
        self.foreign_family = Family.objects.create(name="Andere Familie", slug="commitment-foreign")
        self.owner = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        Membership.objects.create(
            family=self.foreign_family,
            user=self.other,
            role=Membership.Role.OWNER,
            display_name="Fremd",
        )
        self.ledger = get_default_expense_ledger(self.family)
        self.ledger.budget_amount = Decimal("500.00")
        self.ledger.save(update_fields=["budget_amount", "updated_at"])
        self.budget = ExpenseBudget.objects.create(
            family=self.family,
            ledger=self.ledger,
            name="Lebensmittel",
            amount=Decimal("300.00"),
        )
        self.shopping_list = ShoppingList.objects.create(family=self.family, name="Woche")
        self.item = ShoppingItem.objects.create(shopping_list=self.shopping_list, name="Wocheneinkauf")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @property
    def source_url(self):
        return f"/api/budget-commitments/source/shopping_item/{self.item.id}/"

    def test_reservation_reduces_available_without_creating_expense(self):
        response = self.client.put(
            self.source_url,
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "budget": str(self.budget.id),
                "amount": "75.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(BudgetCommitment.objects.filter(status=BudgetCommitment.Status.ACTIVE).count(), 1)

        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(Decimal(summary.data["reserved_amount"]), Decimal("75.00"))
        self.assertEqual(Decimal(summary.data["available_amount"]), Decimal("425.00"))
        category = next(row for row in summary.data["budgets"] if str(row["id"]) == str(self.budget.id))
        self.assertEqual(Decimal(category["reserved_amount"]), Decimal("75.00"))
        self.assertEqual(Decimal(category["available_amount"]), Decimal("225.00"))

    def test_actual_expense_consumes_full_reservation_and_uses_actual_amount(self):
        reserved = self.client.put(
            self.source_url,
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "budget": str(self.budget.id),
                "amount": "100.00",
            },
            format="json",
        ).data["commitment"]
        expense = Expense.objects.create(
            family=self.family,
            ledger=self.ledger,
            title="Wocheneinkauf",
            total_amount=Decimal("83.00"),
            currency="EUR",
            paid_by=self.owner,
            created_by=self.user,
        )
        ExpenseShare.objects.create(expense=expense, member=self.owner, amount=Decimal("83.00"))

        consumed = self.client.post(
            f"/api/budget-commitments/{reserved['id']}/consume/",
            {
                "family": str(self.family.id),
                "expense": str(expense.id),
                "budget": str(self.budget.id),
            },
            format="json",
        )
        self.assertEqual(consumed.status_code, 200, consumed.data)
        commitment = BudgetCommitment.objects.get(id=reserved["id"])
        self.assertEqual(commitment.status, BudgetCommitment.Status.CONSUMED)
        self.assertEqual(commitment.consumed_by_id, expense.id)
        allocation = expense.budget_allocations.get()
        self.assertEqual(allocation.amount_in_budget_currency, Decimal("83.00"))

        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(Decimal(summary.data["reserved_amount"]), Decimal("0.00"))
        self.assertEqual(Decimal(summary.data["spent_amount"]), Decimal("83.00"))
        self.assertEqual(Decimal(summary.data["available_amount"]), Decimal("417.00"))
        category = next(row for row in summary.data["budgets"] if str(row["id"]) == str(self.budget.id))
        self.assertEqual(Decimal(category["spent_amount"]), Decimal("83.00"))
        self.assertEqual(Decimal(category["available_amount"]), Decimal("217.00"))

        retry = self.client.post(
            f"/api/budget-commitments/{reserved['id']}/consume/",
            {
                "family": str(self.family.id),
                "expense": str(expense.id),
                "budget": str(self.budget.id),
            },
            format="json",
        )
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(expense.budget_allocations.count(), 1)

    def test_release_keeps_history_and_restores_availability(self):
        response = self.client.put(
            self.source_url,
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "amount": "40.00",
            },
            format="json",
        )
        commitment_id = response.data["commitment"]["id"]
        released = self.client.delete(f"{self.source_url}?family={self.family.id}")
        self.assertEqual(released.status_code, 200, released.data)
        commitment = BudgetCommitment.objects.get(id=commitment_id)
        self.assertEqual(commitment.status, BudgetCommitment.Status.RELEASED)
        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(Decimal(summary.data["reserved_amount"]), Decimal("0.00"))
        self.assertEqual(Decimal(summary.data["available_amount"]), Decimal("500.00"))

    def test_deleting_source_releases_active_commitment_without_deleting_history(self):
        response = self.client.put(
            self.source_url,
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "budget": str(self.budget.id),
                "amount": "25.00",
            },
            format="json",
        )
        commitment_id = response.data["commitment"]["id"]
        self.item.delete()
        commitment = BudgetCommitment.objects.get(id=commitment_id)
        self.assertEqual(commitment.status, BudgetCommitment.Status.RELEASED)
        self.assertIsNotNone(commitment.released_at)
        summary = self.client.get(f"/api/expense-ledgers/{self.ledger.id}/budget-summary/")
        self.assertEqual(Decimal(summary.data["reserved_amount"]), Decimal("0.00"))
        self.assertEqual(Decimal(summary.data["available_amount"]), Decimal("500.00"))
