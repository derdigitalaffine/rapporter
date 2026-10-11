from django.utils import timezone

from family.context_links import (
    ContextRelationAdapter,
    ContextTypeAdapter,
    UnsupportedContextRelation,
    UnsupportedContextType,
)
from family.models import FamilyEvent, Membership

from .access import visible_decisions_queryset
from .models import Decision


CALENDAR_HIDDEN_EVENT_TYPES = ("weather.current", "weather.forecast")


def _decision_can_link(user, decision):
    if decision.created_by_id == user.id:
        return True
    return Membership.objects.filter(
        family=decision.family,
        user=user,
        role__in=[Membership.Role.OWNER, Membership.Role.ADULT],
    ).exists()


def _decision_lifecycle(decision):
    if decision.closed_at is not None or (decision.closes_at is not None and decision.closes_at <= timezone.now()):
        return "closed"
    return "available"


def register_decision_context(registry):
    try:
        registry.type_adapter("event")
    except UnsupportedContextType:
        registry.register_type(
            ContextTypeAdapter(
                key="event",
                # Match the canonical Calendar feed: weather observations are
                # data/projections, not addressable appointments.
                visible_queryset=lambda user, family: FamilyEvent.objects.filter(family=family).exclude(
                    type__in=CALENDAR_HIDDEN_EVENT_TYPES
                ),
                family_id=lambda obj: obj.family_id,
                deep_link=lambda obj: f"/?page=calendar&event={obj.id}",
            )
        )

    try:
        registry.type_adapter("decision")
    except UnsupportedContextType:
        registry.register_type(
            ContextTypeAdapter(
                key="decision",
                visible_queryset=visible_decisions_queryset,
                family_id=lambda obj: obj.family_id,
                deep_link=lambda obj: f"/?page=decisions&decision={obj.id}",
                lifecycle=_decision_lifecycle,
                can_link=_decision_can_link,
            )
        )

    try:
        registry.relation_adapter("decision.context")
    except UnsupportedContextRelation:
        registry.register_relation(
            ContextRelationAdapter(
                key="decision.context",
                allowed_pairs=frozenset(
                    {
                        ("decision", "task"),
                        ("decision", "note"),
                        ("decision", "trip"),
                        ("decision", "shopping_list"),
                        ("decision", "shopping_item"),
                        ("decision", "board_post"),
                        ("decision", "event"),
                    }
                ),
            )
        )
