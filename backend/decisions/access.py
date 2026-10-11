from django.db.models import Q, Subquery

from family.board_models import BoardPost
from family.context_models import ContextLink
from family.models import FamilyEvent, ShoppingItem, ShoppingList, Task
from family.notes_models import Note
from family.travel_models import Trip

from .models import Decision


CALENDAR_HIDDEN_EVENT_TYPES = ("weather.current", "weather.forecast")


def visible_decisions_queryset(user, family):
    """Return decisions whose optional canonical context remains visible.

    The generic ContextLink registry intentionally does not broaden ACLs. This
    queryset mirrors the currently allow-listed decision contexts so even a
    guessed Decision UUID cannot reveal a context-bound poll after access to its
    source object is lost.
    """

    links = ContextLink.objects.filter(
        family=family,
        source_type="decision",
        relation_key="decision.context",
    )
    visible = Q(context_bound=False)

    context_sets = {
        "task": Task.objects.filter(family=family).exclude(hidden_from_user=user).values("id"),
        "note": Note.objects.filter(family=family)
        .filter(Q(author=user) | Q(shares__user=user))
        .distinct()
        .values("id"),
        "trip": Trip.objects.filter(family=family).values("id"),
        "shopping_list": ShoppingList.objects.filter(family=family).values("id"),
        "shopping_item": ShoppingItem.objects.filter(shopping_list__family=family)
        .exclude(hidden_from_user=user)
        .values("id"),
        "board_post": BoardPost.objects.filter(family=family).values("id"),
        # Keep the decision-context surface aligned with the canonical Calendar
        # feed, where weather observations are not addressable appointments.
        "event": FamilyEvent.objects.filter(family=family)
        .exclude(type__in=CALENDAR_HIDDEN_EVENT_TYPES)
        .values("id"),
    }
    for context_type, context_ids in context_sets.items():
        source_ids = links.filter(
            context_type=context_type,
            context_id__in=Subquery(context_ids),
        ).values("source_id")
        visible |= Q(id__in=Subquery(source_ids))

    return Decision.objects.filter(family=family).filter(visible).distinct()
