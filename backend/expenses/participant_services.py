from decimal import Decimal

from django.db import transaction

from family.models import Membership
from .models import ExpenseBudget
from .money import money
from .participant_models import ExpenseBudgetParticipantPlan


MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT}


def requester_membership(user, family):
    if not user or not user.is_authenticated:
        return None
    return Membership.objects.filter(family=family, user=user).first()


def can_manage_participant_plans(user, family):
    if getattr(user, "is_superuser", False):
        return True
    membership = requester_membership(user, family)
    return bool(membership and membership.role in MANAGER_ROLES)


def _normalized(value):
    return None if value is None else money(Decimal(value))


def requested_plan_signature(rows):
    return {
        str(row["member"]): (
            _normalized(row.get("spending_limit")),
            _normalized(row.get("planned_share")),
        )
        for row in rows
        if row.get("spending_limit") is not None or row.get("planned_share") is not None
    }


def current_plan_signature(budget):
    return {
        str(row.member_id): (
            _normalized(row.spending_limit),
            _normalized(row.planned_share),
        )
        for row in budget.participant_plans.all()
    }


@transaction.atomic
def replace_participant_plans(*, budget, rows, user):
    """Atomically replace current planning rows without touching actual shares/debt."""
    if not can_manage_participant_plans(user, budget.family):
        raise PermissionError("Teilnehmerplanung darf nur von Erwachsenen verwaltet werden.")

    requested = requested_plan_signature(rows)
    member_ids = list(requested)
    members = {
        str(member.id): member
        for member in Membership.objects.select_for_update().filter(
            family=budget.family,
            id__in=member_ids,
        )
    }
    if set(members) != set(member_ids):
        raise ValueError("Mindestens eine Person gehört nicht zu dieser Familie.")

    existing = {
        str(row.member_id): row
        for row in ExpenseBudgetParticipantPlan.objects.select_for_update().filter(budget=budget)
    }

    for member_id, row in list(existing.items()):
        if member_id not in requested:
            row.delete()

    for member_id, (spending_limit, planned_share) in requested.items():
        current = existing.get(member_id)
        if current:
            changed = False
            if current.spending_limit != spending_limit:
                current.spending_limit = spending_limit
                changed = True
            if current.planned_share != planned_share:
                current.planned_share = planned_share
                changed = True
            if changed:
                current.save(update_fields=["spending_limit", "planned_share", "updated_at"])
        else:
            ExpenseBudgetParticipantPlan.objects.create(
                budget=budget,
                member=members[member_id],
                spending_limit=spending_limit,
                planned_share=planned_share,
            )

    return list(
        ExpenseBudgetParticipantPlan.objects.select_related("member", "member__user")
        .filter(budget=budget)
        .order_by("created_at", "id")
    )


def participant_plan_payload(*, budget, user):
    membership = requester_membership(user, budget.family)
    can_manage = can_manage_participant_plans(user, budget.family)
    rows = []
    for row in (
        ExpenseBudgetParticipantPlan.objects.select_related("member", "member__user")
        .filter(budget=budget)
        .order_by("created_at", "id")
    ):
        can_view_limit = can_manage or bool(membership and membership.id == row.member_id)
        rows.append(
            {
                "member": str(row.member_id),
                "member_name": row.member.display_name or row.member.user.username,
                "planned_share": None if row.planned_share is None else str(row.planned_share),
                "spending_limit": None if not can_view_limit or row.spending_limit is None else str(row.spending_limit),
                "spending_limit_visible": can_view_limit,
            }
        )
    return {
        "budget": str(budget.id),
        "currency": budget.ledger.base_currency.upper(),
        "can_manage": can_manage,
        "plans": rows,
    }
