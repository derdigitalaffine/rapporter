from family.context_links import (
    ContextRelationAdapter,
    ContextTypeAdapter,
    UnsupportedContextRelation,
    UnsupportedContextType,
    default_context_registry,
)
from family.models import Family, Membership

from .models import ExpenseLedger
from entitlements.services import has_capability


def _visible_ledgers(user, family):
    if not user or not user.is_authenticated:
        return ExpenseLedger.objects.none()
    membership = Membership.objects.filter(
        user=user,
        family=family,
        family__status=Family.Status.ACTIVE,
    ).first()
    if not membership or not has_capability(family, "expenses"):
        return ExpenseLedger.objects.none()
    return ExpenseLedger.objects.filter(family=family)


def _ledger_lifecycle(ledger):
    return "archived" if ledger.archived else "available"


def _can_manage_ledger_link(user, ledger):
    return Membership.objects.filter(
        user=user,
        family_id=ledger.family_id,
        family__status=Family.Status.ACTIVE,
    ).exclude(role=Membership.Role.GUEST).exists()


def _can_create_trip_relation(membership, ledger, trip):
    return (
        membership.role != Membership.Role.GUEST
        and not ledger.archived
        and not trip.archived
    )


def _register_type(registry, adapter):
    try:
        registry.type_adapter(adapter.key)
    except UnsupportedContextType:
        registry.register_type(adapter)


def _register_relation(registry, adapter):
    try:
        registry.relation_adapter(adapter.key)
    except UnsupportedContextRelation:
        registry.register_relation(adapter)


def register_expense_context_adapters(registry=None):
    registry = registry or default_context_registry()
    _register_type(
        registry,
        ContextTypeAdapter(
            key="expense_ledger",
            visible_queryset=_visible_ledgers,
            family_id=lambda ledger: ledger.family_id,
            deep_link=lambda ledger: "/?page=expenses",
            lifecycle=_ledger_lifecycle,
            can_link=_can_manage_ledger_link,
        ),
    )
    _register_relation(
        registry,
        ContextRelationAdapter(
            key="expense.trip",
            allowed_pairs=frozenset({("expense_ledger", "trip")}),
            can_create=_can_create_trip_relation,
        ),
    )
    return registry
