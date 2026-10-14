from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family, Membership
from .commitment_models import BudgetCommitment
from .models import Expense, ExpenseBudget, ExpenseBudgetAllocation, get_default_expense_ledger
from .period_models import ExpenseBudgetPeriod
from .period_services import configure_current_period, ensure_budget_period, period_state


User = get_user_model()
UTC = ZoneInfo("UTC")


class BudgetPeriodTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="period-owner", password="test")
        self.family = Family.objects.create(name="Perioden Familie", slug="perioden-family")
        self.owner = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.ledger = get_default_expense_ledger(self.family)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def budget(self, *, amount="100.00", period_type=ExpenseBudget.PeriodType.MONTH):
        return ExpenseBudget.objects.create(
            family=self.family,
            ledger=self.ledger,
            name="Spartopf",
            amount=Decimal(amount),
            period_type=period_type,
        )

    def spend(self, budget, amount, occurred_on):
        expense = Expense.objects.create(
            family=self.family,
            ledger=self.ledger,
            title="Ausgabe",
            total_amount=Decimal(amount),
            currency="EUR",
            occurred_at=datetime(occurred_on.year, occurred_on.month, occurred_on.day, 12, tzinfo=UTC),
            paid_by=self.owner,
            created_by=self.user,
        )
        ExpenseBudgetAllocation.objects.create(
            expense=expense,
            budget=budget,
            amount_in_budget_currency=Decimal(amount),
        )
        return expense

    def test_month_carry_uses_actual_spend_but_not_active_reservation(self):
        budget = self.budget()
        january = configure_current_period(
            budget,
            rollover_policy=ExpenseBudgetPeriod.RolloverPolicy.CARRY_POSITIVE,
            as_of=date(2026, 1, 10),
        )
        self.assertEqual(january.planned_amount, Decimal("100.00"))
        self.spend(budget, "60.00", date(2026, 1, 20))
        BudgetCommitment.objects.create(
            family=self.family,
            ledger=self.ledger,
            budget=budget,
            source_type="shopping_item",
            source_id=uuid4(),
            amount=Decimal("20.00"),
            currency="EUR",
            created_by=self.user,
        )

        february = ensure_budget_period(budget, as_of=date(2026, 2, 2))
        january.refresh_from_db()
        self.assertIsNotNone(january.closed_at)
        self.assertEqual(february.carryover_amount, Decimal("40.00"))
        self.assertEqual(february.rollover_policy, ExpenseBudgetPeriod.RolloverPolicy.CARRY_POSITIVE)
        self.assertEqual(BudgetCommitment.objects.filter(budget=budget, status="active").count(), 1)

        state = period_state(budget, as_of=date(2026, 2, 2))
        self.assertEqual(state["spent_amount"], Decimal("0.00"))
        # The 20 EUR commitment remains active and is deducted separately by
        # the summary: 100 plan + 40 carry - 20 reserved = 120 available.
        self.assertEqual(state["planned_amount"] + state["carryover_amount"] - Decimal("20.00"), Decimal("120.00"))

    def test_reset_and_overspend_never_create_negative_carry(self):
        reset_budget = self.budget()
        configure_current_period(reset_budget, rollover_policy=ExpenseBudgetPeriod.RolloverPolicy.RESET, as_of=date(2026, 1, 5))
        self.spend(reset_budget, "20.00", date(2026, 1, 8))
        reset_february = ensure_budget_period(reset_budget, as_of=date(2026, 2, 1))
        self.assertEqual(reset_february.carryover_amount, Decimal("0.00"))

        overspent = ExpenseBudget.objects.create(
            family=self.family,
            ledger=self.ledger,
            name="Limit",
            amount=Decimal("100.00"),
            period_type=ExpenseBudget.PeriodType.MONTH,
        )
        configure_current_period(overspent, rollover_policy=ExpenseBudgetPeriod.RolloverPolicy.CARRY_POSITIVE, as_of=date(2026, 1, 5))
        self.spend(overspent, "120.00", date(2026, 1, 12))
        overspent_february = ensure_budget_period(overspent, as_of=date(2026, 2, 1))
        self.assertEqual(overspent_february.carryover_amount, Decimal("0.00"))

    def test_rollover_is_idempotent_and_closed_snapshot_stays_immutable(self):
        budget = self.budget()
        january = configure_current_period(
            budget,
            rollover_policy=ExpenseBudgetPeriod.RolloverPolicy.CARRY_POSITIVE,
            as_of=date(2026, 1, 15),
        )
        self.spend(budget, "60.00", date(2026, 1, 20))
        first = ensure_budget_period(budget, as_of=date(2026, 2, 3))
        second = ensure_budget_period(budget, as_of=date(2026, 2, 3))
        self.assertEqual(first.id, second.id)
        self.assertEqual(ExpenseBudgetPeriod.objects.filter(budget=budget).count(), 2)

        budget.amount = Decimal("150.00")
        budget.save(update_fields=["amount", "updated_at"])
        configure_current_period(budget, as_of=date(2026, 2, 3))
        january.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(january.planned_amount, Decimal("100.00"))
        self.assertEqual(january.carryover_amount, Decimal("0.00"))
        self.assertEqual(first.planned_amount, Decimal("150.00"))
        self.assertEqual(first.carryover_amount, Decimal("40.00"))

    def test_date_range_scopes_spend_without_creating_recurring_snapshots(self):
        budget = ExpenseBudget.objects.create(
            family=self.family,
            ledger=self.ledger,
            name="Projekt",
            amount=Decimal("300.00"),
            period_type=ExpenseBudget.PeriodType.DATE_RANGE,
            starts_on=date(2026, 1, 1),
            ends_on=date(2026, 1, 31),
        )
        self.spend(budget, "40.00", date(2026, 1, 10))
        self.spend(budget, "70.00", date(2026, 2, 10))
        state = period_state(budget, as_of=date(2026, 2, 15))
        self.assertEqual(state["spent_amount"], Decimal("40.00"))
        self.assertEqual(state["carryover_amount"], Decimal("0.00"))
        self.assertEqual(ExpenseBudgetPeriod.objects.filter(budget=budget).count(), 0)

    def test_api_accepts_rollover_policy_and_exposes_current_period(self):
        family_tz = ZoneInfo(self.family.timezone)
        today = timezone.localtime(timezone.now(), family_tz).date()
        response = self.client.post(
            "/api/expense-budgets/",
            {
                "family": str(self.family.id),
                "ledger": str(self.ledger.id),
                "name": "Monatslimit",
                "amount": "250.00",
                "period_type": "month",
                "rollover_policy": "carry_positive",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["rollover_policy"], "carry_positive")
        self.assertEqual(response.data["carryover_amount"], "0.00")
        self.assertEqual(str(response.data["period_starts_on"]), str(today.replace(day=1)))
        self.assertIsNotNone(response.data["period_ends_on"])
