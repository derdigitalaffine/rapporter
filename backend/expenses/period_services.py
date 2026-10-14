import calendar
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Expense, ExpenseBudget
from .money import money
from .period_models import ExpenseBudgetPeriod


RECURRING_PERIOD_TYPES = {
    ExpenseBudget.PeriodType.MONTH,
    ExpenseBudget.PeriodType.YEAR,
}


def _family_local_date(budget):
    timezone_name = getattr(getattr(budget, "family", None), "timezone", None) or "UTC"
    try:
        family_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        family_tz = ZoneInfo("UTC")
    return timezone.localtime(timezone.now(), family_tz).date()


def _calendar_bounds(period_type, day):
    if period_type == ExpenseBudget.PeriodType.MONTH:
        last_day = calendar.monthrange(day.year, day.month)[1]
        return date(day.year, day.month, 1), date(day.year, day.month, last_day)
    if period_type == ExpenseBudget.PeriodType.YEAR:
        return date(day.year, 1, 1), date(day.year, 12, 31)
    return None, None


def _next_bounds(period_type, prior_end):
    return _calendar_bounds(period_type, prior_end + timedelta(days=1))


def _spent_for_bounds(budget, starts_on=None, ends_on=None):
    cached = getattr(budget, "_budget_spent_amount", None)
    if starts_on is None and ends_on is None and cached is not None:
        return money(cached)
    allocations = budget.allocations.filter(expense__status=Expense.Status.POSTED)
    if starts_on:
        allocations = allocations.filter(expense__occurred_at__date__gte=starts_on)
    if ends_on:
        allocations = allocations.filter(expense__occurred_at__date__lte=ends_on)
    total = allocations.aggregate(total=Sum("amount_in_budget_currency"))["total"] or Decimal("0.00")
    return money(total)


def _close_period(period):
    if period.closed_at:
        return period
    period.closed_at = timezone.now()
    period.save(update_fields=["closed_at", "updated_at"])
    return period


def _carry_from_period(period):
    if period.rollover_policy != ExpenseBudgetPeriod.RolloverPolicy.CARRY_POSITIVE:
        return Decimal("0.00")
    spent = _spent_for_bounds(period.budget, period.starts_on, period.ends_on)
    unused = money(period.planned_amount + period.carryover_amount - spent)
    return money(max(unused, Decimal("0.00")))


@transaction.atomic
def ensure_budget_period(budget, as_of=None):
    """Return the active recurring period, lazily closing/rolling expired periods."""
    budget = ExpenseBudget.objects.select_for_update().select_related("family").get(pk=budget.pk)
    day = as_of or _family_local_date(budget)
    if budget.period_type not in RECURRING_PERIOD_TYPES:
        return None

    target_start, target_end = _calendar_bounds(budget.period_type, day)
    existing = ExpenseBudgetPeriod.objects.filter(
        budget=budget,
        period_type=budget.period_type,
        starts_on=target_start,
        ends_on=target_end,
    ).first()
    if existing:
        return existing

    latest = ExpenseBudgetPeriod.objects.filter(
        budget=budget,
        period_type=budget.period_type,
    ).order_by("-ends_on", "-created_at").first()

    if latest is None or latest.starts_on > day:
        period, _ = ExpenseBudgetPeriod.objects.get_or_create(
            budget=budget,
            period_type=budget.period_type,
            starts_on=target_start,
            ends_on=target_end,
            defaults={
                "planned_amount": money(budget.amount),
                "carryover_amount": Decimal("0.00"),
                "rollover_policy": ExpenseBudgetPeriod.RolloverPolicy.RESET,
            },
        )
        return period

    while latest.ends_on < day:
        carryover = _carry_from_period(latest)
        policy = latest.rollover_policy
        _close_period(latest)
        starts_on, ends_on = _next_bounds(budget.period_type, latest.ends_on)
        latest, _ = ExpenseBudgetPeriod.objects.get_or_create(
            budget=budget,
            period_type=budget.period_type,
            starts_on=starts_on,
            ends_on=ends_on,
            defaults={
                "planned_amount": money(budget.amount),
                "carryover_amount": carryover,
                "rollover_policy": policy,
            },
        )
    return latest


def period_state(budget, as_of=None):
    """Return period-aware planning facts without folding active commitments into carryover."""
    day = as_of or _family_local_date(budget)
    if budget.period_type in RECURRING_PERIOD_TYPES:
        period = ensure_budget_period(budget, as_of=day)
        return {
            "period_type": budget.period_type,
            "starts_on": period.starts_on,
            "ends_on": period.ends_on,
            "planned_amount": money(period.planned_amount),
            "carryover_amount": money(period.carryover_amount),
            "rollover_policy": period.rollover_policy,
            "spent_amount": _spent_for_bounds(budget, period.starts_on, period.ends_on),
            "closed_at": period.closed_at,
        }

    starts_on = budget.starts_on if budget.period_type in {ExpenseBudget.PeriodType.DATE_RANGE, ExpenseBudget.PeriodType.CONTEXT} else None
    ends_on = budget.ends_on if budget.period_type in {ExpenseBudget.PeriodType.DATE_RANGE, ExpenseBudget.PeriodType.CONTEXT} else None
    return {
        "period_type": budget.period_type,
        "starts_on": starts_on,
        "ends_on": ends_on,
        "planned_amount": money(budget.amount),
        "carryover_amount": Decimal("0.00"),
        "rollover_policy": None,
        "spent_amount": _spent_for_bounds(budget, starts_on, ends_on),
        "closed_at": None,
    }


@transaction.atomic
def configure_current_period(budget, rollover_policy=None, as_of=None):
    """Sync the mutable active snapshot after a budget plan edit."""
    if budget.period_type not in RECURRING_PERIOD_TYPES:
        return None
    period = ensure_budget_period(budget, as_of=as_of)
    if period.closed_at:
        return period
    fields = []
    planned = money(budget.amount)
    if period.planned_amount != planned:
        period.planned_amount = planned
        fields.append("planned_amount")
    if rollover_policy is not None and period.rollover_policy != rollover_policy:
        period.rollover_policy = rollover_policy
        fields.append("rollover_policy")
    if fields:
        period.save(update_fields=[*fields, "updated_at"])
    return period


def validate_period_type_change(budget, next_period_type):
    if not budget or next_period_type == budget.period_type:
        return
    if ExpenseBudgetPeriod.objects.filter(budget=budget).exists():
        raise ValueError(
            "Der Periodentyp kann nach Beginn einer Budgetperiode nicht mehr geändert werden. "
            "Archiviere den Topf und lege für einen neuen Rhythmus einen neuen an."
        )
