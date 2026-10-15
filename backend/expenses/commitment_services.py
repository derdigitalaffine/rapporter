from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from family.models import ShoppingItem
from .budget_services import replace_budget_allocations
from .commitment_models import BudgetCommitment
from .models import Expense, ExpenseBudget, ExpenseLedger, get_default_expense_ledger
from .money import money


SUPPORTED_SOURCES = {"shopping_item"}


def _lock_source(family, source_type, source_id):
    if source_type not in SUPPORTED_SOURCES:
        raise ValueError("Diese Reservierungsquelle wird nicht unterstützt.")
    if source_type == "shopping_item":
        source = (
            ShoppingItem.objects.select_for_update()
            .select_related("shopping_list")
            .filter(id=source_id, shopping_list__family=family)
            .first()
        )
        if not source:
            raise ValueError("Der Einkaufsartikel ist für diese Familie nicht verfügbar.")
        return source
    return None


def _ledger(family, ledger_id):
    try:
        return ExpenseLedger.objects.select_for_update().get(id=ledger_id, family=family, archived=False)
    except ExpenseLedger.DoesNotExist as exc:
        raise ValueError("Der Abrechnungskreis ist nicht verfügbar.") from exc


def _budget(family, ledger, budget_id):
    if not budget_id:
        return None
    try:
        return ExpenseBudget.objects.get(id=budget_id, family=family, ledger=ledger, archived=False)
    except ExpenseBudget.DoesNotExist as exc:
        raise ValueError("Der Budgettopf ist nicht verfügbar.") from exc


@transaction.atomic
def upsert_budget_commitment(*, user, family, source_type, source_id, ledger_id, amount, budget_id=None):
    _lock_source(family, source_type, source_id)
    ledger = _ledger(family, ledger_id)
    budget = _budget(family, ledger, budget_id)
    amount = money(amount)
    if amount <= Decimal("0.00"):
        raise ValueError("Der vorgemerkte Betrag muss größer als 0 sein.")

    commitment = (
        BudgetCommitment.objects.select_for_update()
        .filter(
            family=family,
            source_type=source_type,
            source_id=source_id,
            status=BudgetCommitment.Status.ACTIVE,
        )
        .first()
    )
    if commitment is None:
        return BudgetCommitment.objects.create(
            family=family,
            ledger=ledger,
            budget=budget,
            source_type=source_type,
            source_id=source_id,
            amount=amount,
            currency=ledger.base_currency.upper(),
            created_by=user,
        )
    commitment.ledger = ledger
    commitment.budget = budget
    commitment.amount = amount
    commitment.currency = ledger.base_currency.upper()
    commitment.save(update_fields=["ledger", "budget", "amount", "currency", "updated_at"])
    return commitment


@transaction.atomic
def release_budget_commitment(commitment):
    commitment = BudgetCommitment.objects.select_for_update().get(pk=commitment.pk)
    if commitment.status != BudgetCommitment.Status.ACTIVE:
        return commitment
    commitment.status = BudgetCommitment.Status.RELEASED
    commitment.released_at = timezone.now()
    commitment.save(update_fields=["status", "released_at", "updated_at"])
    return commitment


@transaction.atomic
def consume_budget_commitment(*, commitment, expense, budget_id=None):
    # Lock only canonical rows. Expense.ledger is nullable and must not be part
    # of a select_related() FOR UPDATE outer join on PostgreSQL.
    commitment = BudgetCommitment.objects.select_for_update().get(pk=commitment.pk)
    expense = Expense.objects.select_for_update().get(pk=expense.pk)

    if commitment.status == BudgetCommitment.Status.CONSUMED:
        if commitment.consumed_by_id == expense.id:
            return commitment
        raise ValueError("Diese Vormerkung wurde bereits durch eine andere Ausgabe verbraucht.")
    if commitment.status != BudgetCommitment.Status.ACTIVE:
        raise ValueError("Diese Vormerkung ist nicht mehr aktiv.")
    if expense.status != Expense.Status.POSTED or expense.total_amount is None:
        raise ValueError("Nur eine gebuchte Ausgabe kann eine Vormerkung verbrauchen.")
    if expense.family_id != commitment.family_id:
        raise ValueError("Ausgabe und Vormerkung gehören nicht zur selben Familie.")

    ledger = expense.ledger or get_default_expense_ledger(expense.family)
    if ledger.id != commitment.ledger_id:
        raise ValueError("Ausgabe und Vormerkung müssen denselben Abrechnungskreis verwenden.")
    if expense.currency.upper() != commitment.currency.upper():
        raise ValueError("Die Ausgabe muss in der Basiswährung der Vormerkung gebucht sein.")

    rows = [] if not budget_id else [{"budget": budget_id, "amount_in_budget_currency": expense.total_amount}]
    replace_budget_allocations(expense, rows)

    commitment.status = BudgetCommitment.Status.CONSUMED
    commitment.consumed_by = expense
    commitment.consumed_at = timezone.now()
    commitment.save(update_fields=["status", "consumed_by", "consumed_at", "updated_at"])
    return commitment
