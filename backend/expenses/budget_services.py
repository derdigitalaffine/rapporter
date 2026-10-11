from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from .models import Expense, ExpenseBudget, ExpenseBudgetAllocation, get_default_expense_ledger
from .money import _ledger_scope, money


@transaction.atomic
def replace_budget_allocations(expense, rows):
    """Atomically replace all budget allocations for one posted expense."""
    expense = (
        Expense.objects.select_for_update()
        .select_related("family", "ledger")
        .get(pk=expense.pk)
    )
    if expense.status != Expense.Status.POSTED or expense.total_amount is None:
        raise ValueError("Budgetzuordnung ist nur für gebuchte Ausgaben mit Betrag möglich.")

    ledger = expense.ledger or get_default_expense_ledger(expense.family)
    if expense.ledger_id is None:
        expense.ledger = ledger
        expense.save(update_fields=["ledger", "updated_at"])

    if expense.currency.upper() != ledger.base_currency.upper():
        raise ValueError(
            "Budgetzuordnung benötigt die Ledger-Basiswährung; Fremdwährungsumrechnung ist noch nicht aktiviert."
        )

    if not rows:
        expense.budget_allocations.all().delete()
        return expense, []

    budget_ids = [row["budget"] for row in rows]
    if len(budget_ids) != len(set(budget_ids)):
        raise ValueError("Jeder Budgettopf darf pro Ausgabe nur einmal vorkommen.")

    budgets = {
        budget.id: budget
        for budget in ExpenseBudget.objects.filter(
            id__in=budget_ids,
            family=expense.family,
            ledger=ledger,
            archived=False,
        )
    }
    if len(budgets) != len(budget_ids):
        raise ValueError("Mindestens ein Budgettopf ist für diese Ausgabe nicht verfügbar.")

    normalized = []
    for row in rows:
        amount = money(row["amount_in_budget_currency"])
        if amount <= 0:
            raise ValueError("Budgetanteile müssen größer als 0 sein.")
        normalized.append((budgets[row["budget"]], amount))

    allocated_total = money(sum((amount for _, amount in normalized), Decimal("0.00")))
    expense_total = money(expense.total_amount)
    if allocated_total != expense_total:
        raise ValueError(
            f"Budgetanteile müssen zusammen exakt {expense_total:.2f} {ledger.base_currency.upper()} ergeben."
        )

    # Delete only after all validation succeeds so a rejected replacement leaves
    # the prior, valid allocation set intact.
    expense.budget_allocations.all().delete()
    ExpenseBudgetAllocation.objects.bulk_create(
        [
            ExpenseBudgetAllocation(
                expense=expense,
                budget=budget,
                amount_in_budget_currency=amount,
            )
            for budget, amount in normalized
        ]
    )
    allocations = list(
        expense.budget_allocations.select_related("budget", "budget__ledger").order_by("created_at")
    )
    return expense, allocations


def ledger_budget_summary(ledger):
    expenses = Expense.objects.filter(
        _ledger_scope(ledger),
        family=ledger.family,
        status=Expense.Status.POSTED,
    ).exclude(total_amount__isnull=True)

    spent = (
        expenses.filter(currency__iexact=ledger.base_currency).aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0.00")
    )
    spent = money(spent)
    unconverted_count = expenses.exclude(currency__iexact=ledger.base_currency).count()

    overall_budget = money(ledger.budget_amount) if ledger.budget_amount is not None else None
    remaining = money(overall_budget - spent) if overall_budget is not None else None

    return {
        "currency": ledger.base_currency.upper(),
        "budget_amount": overall_budget,
        "spent_amount": spent,
        "remaining_amount": remaining,
        "over_budget": bool(overall_budget is not None and spent > overall_budget),
        "unconverted_expense_count": unconverted_count,
    }
