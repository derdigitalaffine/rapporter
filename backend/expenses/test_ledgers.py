from decimal import Decimal
import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership
from .models import Expense, ExpenseLedger, ExpenseShare, Settlement, get_default_expense_ledger
from .money import balance_summary

User = get_user_model()


class ExpenseLedgerCoreTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ledger-alex", password="test")
        self.other = User.objects.create_user(username="ledger-sam", password="test")
        self.family = Family.objects.create(name="Ledger Familie", slug="ledger-familie")
        self.other_family = Family.objects.create(name="Andere Ledger Familie", slug="andere-ledger-familie")
        self.alex = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.sam = Membership.objects.create(
            family=self.family,
            user=self.other,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        self.alex_other = Membership.objects.create(
            family=self.other_family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _expense(self, *, ledger, total):
        expense = Expense.objects.create(
            family=self.family,
            ledger=ledger,
            title="Test",
            total_amount=total,
            currency="EUR",
            paid_by=self.alex,
            created_by=self.user,
        )
        half = Decimal(total) / Decimal("2")
        ExpenseShare.objects.create(expense=expense, member=self.alex, amount=half)
        ExpenseShare.objects.create(expense=expense, member=self.sam, amount=half)
        return expense

    def test_expense_api_assigns_default_ledger_when_omitted(self):
        response = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "title": "Einkauf",
                "total_amount": "12.00",
                "currency": "EUR",
                "participants": [str(self.alex.id), str(self.sam.id)],
                "split_type": "equal",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        expense = Expense.objects.get(id=response.data["id"])
        self.assertIsNotNone(expense.ledger_id)
        self.assertTrue(expense.ledger.is_default)
        self.assertEqual(response.data["ledger"], expense.ledger_id)

    def test_cross_family_ledger_is_rejected_on_expense_write(self):
        foreign = ExpenseLedger.objects.create(
            family=self.other_family,
            name="Fremd",
            base_currency="EUR",
        )
        response = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "ledger": str(foreign.id),
                "title": "Nicht erlaubt",
                "total_amount": "12.00",
                "currency": "EUR",
                "participants": [str(self.alex.id), str(self.sam.id)],
                "split_type": "equal",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("ledger", response.data)
        self.assertEqual(Expense.objects.count(), 0)

    def test_two_ledgers_have_independent_balances_and_settlements(self):
        default = get_default_expense_ledger(self.family)
        travel = ExpenseLedger.objects.create(
            family=self.family,
            name="Japan 2027",
            base_currency="EUR",
        )
        self._expense(ledger=default, total="20.00")
        self._expense(ledger=travel, total="60.00")

        default_summary = balance_summary(self.family, "EUR", ledger=default)
        travel_summary = balance_summary(self.family, "EUR", ledger=travel)
        self.assertEqual(default_summary[str(self.sam.id)]["balance"], Decimal("-10.00"))
        self.assertEqual(travel_summary[str(self.sam.id)]["balance"], Decimal("-30.00"))

        response = self.client.post(
            "/api/expenses/settlements/",
            {
                "family": str(self.family.id),
                "ledger": str(travel.id),
                "from_member": str(self.sam.id),
                "to_member": str(self.alex.id),
                "amount": "30.00",
                "currency": "EUR",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

        default_summary = balance_summary(self.family, "EUR", ledger=default)
        travel_summary = balance_summary(self.family, "EUR", ledger=travel)
        self.assertEqual(default_summary[str(self.sam.id)]["balance"], Decimal("-10.00"))
        self.assertEqual(travel_summary[str(self.sam.id)]["balance"], Decimal("0.00"))

    def test_balance_endpoint_defaults_to_family_ledger_and_accepts_explicit_ledger(self):
        default = get_default_expense_ledger(self.family)
        travel = ExpenseLedger.objects.create(
            family=self.family,
            name="Reise",
            base_currency="EUR",
        )
        self._expense(ledger=default, total="20.00")
        self._expense(ledger=travel, total="60.00")

        default_response = self.client.get(
            "/api/expenses/balance/",
            {"family": str(self.family.id), "currency": "EUR"},
        )
        self.assertEqual(default_response.status_code, 200, default_response.data)
        self.assertEqual(default_response.data["ledger"], str(default.id))
        self.assertEqual(default_response.data["open_amount"], "10.00")

        travel_response = self.client.get(
            "/api/expenses/balance/",
            {"family": str(self.family.id), "ledger": str(travel.id), "currency": "EUR"},
        )
        self.assertEqual(travel_response.status_code, 200, travel_response.data)
        self.assertEqual(travel_response.data["open_amount"], "30.00")

    def test_cross_family_ledger_is_rejected_on_balance_read(self):
        foreign = ExpenseLedger.objects.create(
            family=self.other_family,
            name="Fremd",
            base_currency="EUR",
        )
        response = self.client.get(
            "/api/expenses/balance/",
            {"family": str(self.family.id), "ledger": str(foreign.id)},
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("ledger", response.data)

    def test_soft_budget_does_not_block_expense(self):
        ledger = ExpenseLedger.objects.create(
            family=self.family,
            name="Haushalt",
            base_currency="EUR",
            budget_amount=Decimal("5.00"),
        )
        response = self.client.post(
            "/api/expenses/",
            {
                "family": str(self.family.id),
                "ledger": str(ledger.id),
                "title": "Über Budget",
                "total_amount": "12.00",
                "currency": "EUR",
                "participants": [str(self.alex.id), str(self.sam.id)],
                "split_type": "equal",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Expense.objects.get(id=response.data["id"]).ledger_id, ledger.id)

    def test_data_migration_backfills_existing_rows_without_changing_amounts(self):
        expense = Expense.objects.create(
            family=self.family,
            ledger=None,
            title="Legacy",
            total_amount=Decimal("20.00"),
            currency="EUR",
            paid_by=self.alex,
            created_by=self.user,
        )
        share_a = ExpenseShare.objects.create(expense=expense, member=self.alex, amount=Decimal("10.00"))
        share_b = ExpenseShare.objects.create(expense=expense, member=self.sam, amount=Decimal("10.00"))
        settlement = Settlement.objects.create(
            family=self.family,
            ledger=None,
            from_member=self.sam,
            to_member=self.alex,
            amount=Decimal("4.25"),
            currency="EUR",
            created_by=self.user,
        )

        migration = importlib.import_module("expenses.migrations.0005_expense_ledgers")
        migration.backfill_default_ledgers(django_apps, None)
        migration.backfill_default_ledgers(django_apps, None)

        expense.refresh_from_db()
        settlement.refresh_from_db()
        share_a.refresh_from_db()
        share_b.refresh_from_db()
        self.assertIsNotNone(expense.ledger_id)
        self.assertEqual(expense.ledger_id, settlement.ledger_id)
        self.assertTrue(expense.ledger.is_default)
        self.assertEqual(expense.total_amount, Decimal("20.00"))
        self.assertEqual(share_a.amount + share_b.amount, Decimal("20.00"))
        self.assertEqual(settlement.amount, Decimal("4.25"))
        self.assertEqual(ExpenseLedger.objects.filter(family=self.family, is_default=True).count(), 1)
        self.assertEqual(ExpenseLedger.objects.filter(family=self.other_family, is_default=True).count(), 1)
