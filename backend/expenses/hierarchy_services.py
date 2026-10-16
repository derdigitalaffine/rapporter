"""Read-only hierarchy projection over the canonical inclusive budget envelopes."""
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .commitment_models import BudgetCommitment
from .models import Expense, ExpenseBudget, ExpenseBudgetAllocation
from .money import money

ZERO = Decimal('0.00')


def budget_hierarchy(ledger, budget_data, summary):
    """Keep direct legacy fields intact; aggregate each node in its own period.

    Archived nodes are transparent for the active tree. Their allocations stay
    in the nearest active ancestor's miscellaneous bucket, never disappear.
    The ledger root uses its existing all-time/base-currency spending contract.
    """
    models = {str(b.id): b for b in ExpenseBudget.objects.filter(ledger=ledger, family=ledger.family)}
    active = {str(row['id']): row for row in budget_data}
    parents = {}
    for key, row in active.items():
        parent = str(row['parent']) if row['parent'] else None
        seen = {key}
        while parent and parent not in active:
            if parent in seen or parent not in models:
                parent = None
                break
            seen.add(parent)
            parent = str(models[parent].parent_id) if models[parent].parent_id else None
        parents[key] = parent if parent not in seen else None
    children = {key: [] for key in [None, *active]}
    for key, parent in parents.items():
        children[parent].append(key)

    # Associate every allocation/reservation with its closest active node.
    def owner(key):
        seen = set()
        while key and key not in active:
            if key in seen or key not in models:
                return None
            seen.add(key)
            key = str(models[key].parent_id) if models[key].parent_id else None
        return key

    allocations = list(ExpenseBudgetAllocation.objects.filter(
        budget__ledger=ledger, budget__family=ledger.family,
        expense__family=ledger.family, expense__status=Expense.Status.POSTED,
    ).values_list('budget_id', 'amount_in_budget_currency', 'expense__occurred_at', 'expense__currency'))
    reservations = list(BudgetCommitment.objects.filter(
        ledger=ledger, family=ledger.family, status=BudgetCommitment.Status.ACTIVE,
        currency=ledger.base_currency.upper(),
    ).values_list('budget_id', 'amount'))
    try:
        local_tz = ZoneInfo(getattr(ledger.family, 'timezone', None) or 'UTC')
    except ZoneInfoNotFoundError:
        local_tz = ZoneInfo('UTC')

    def subtree(key):
        found, pending = set(), [key]
        while pending:
            current = pending.pop()
            if current in found:
                continue
            found.add(current)
            pending.extend(children.get(current, []))
        return found

    def project(key, row, planned, spent=None, reserved=None):
        ids = subtree(key)
        start, end = row.get('period_starts_on'), row.get('period_ends_on')
        def in_period(occurred):
            day = occurred.astimezone(local_tz).date()
            return (not start or str(day) >= str(start)) and (not end or str(day) <= str(end))
        scoped = [(owner(str(b)), amount) for b, amount, occurred, currency in allocations if in_period(occurred) and (key is not None or currency.upper() == ledger.base_currency.upper())]
        scoped_reservations = [(owner(str(b)) if b else None, amount) for b, amount in reservations]
        if spent is None:
            spent = money(sum((amount for b, amount in scoped if b in ids), ZERO))
        if reserved is None:
            reserved = money(sum((amount for b, amount in scoped_reservations if b in ids), ZERO))
        # Root includes native/unallocated/archived spending too. Subtract the
        # child branches in the ROOT period, not their independent snapshots.
        child_ids = ids - {key}
        child_spent = money(sum((amount for b, amount in scoped if b in child_ids), ZERO))
        child_reserved = money(sum((amount for b, amount in scoped_reservations if b in child_ids), ZERO))
        child_plan = money(sum((money(active[b]['amount']) for b in children[key]), ZERO))
        miscellaneous = None if planned is None else money(planned - child_plan)
        carry = money(row.get('carryover_amount') or ZERO)
        child_carry = money(sum((money(active[b].get('carryover_amount') or ZERO) for b in children[key]), ZERO))
        misc_carry = money(carry - child_carry)
        available = None if planned is None else money(planned + carry - spent - reserved)
        misc_spent, misc_reserved = money(spent - child_spent), money(reserved - child_reserved)
        misc_available = None if miscellaneous is None else money(miscellaneous + misc_carry - misc_spent - misc_reserved)
        return {
            'parent': parents.get(key), 'children_amount': str(child_plan),
            'miscellaneous_amount': None if miscellaneous is None else str(miscellaneous),
            'spent_amount': str(spent), 'reserved_amount': str(reserved),
            'available_amount': None if available is None else str(available),
            'miscellaneous_carryover_amount': str(misc_carry),
            'miscellaneous_spent_amount': str(misc_spent),
            'miscellaneous_reserved_amount': str(misc_reserved),
            'miscellaneous_available_amount': None if misc_available is None else str(misc_available),
            'overplanned': miscellaneous is not None and miscellaneous < ZERO,
            'over_available': available is not None and available < ZERO,
        }

    for key, row in active.items():
        row['hierarchy'] = project(key, row, money(row['amount']))
    return project(None, {}, summary['budget_amount'], summary['spent_amount'], summary['reserved_amount'])


def direct_child_plan(scope):
    """Inclusive child envelopes, skipping archived intermediates."""
    ledger = scope if hasattr(scope, 'budget_amount') else scope.ledger
    target = None if hasattr(scope, 'budget_amount') else scope.pk
    budgets = {b.pk: b for b in ExpenseBudget.objects.filter(ledger=ledger, family=ledger.family)}
    total = ZERO
    for budget in budgets.values():
        if budget.archived:
            continue
        parent, seen = budget.parent_id, {budget.pk}
        while parent and parent in budgets and budgets[parent].archived:
            if parent in seen:
                parent = None
                break
            seen.add(parent)
            parent = budgets[parent].parent_id
        if parent == target:
            total += budget.amount
    return money(total)


def check_child_plan(scope, expected):
    if expected is not None and direct_child_plan(scope) != expected:
        from .planning_serializers import BudgetPlanningConflict
        raise BudgetPlanningConflict()
