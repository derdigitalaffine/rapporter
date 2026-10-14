from .context_links import ContextRelationAdapter, ContextTypeAdapter, default_context_registry
from .models import ShoppingItem
from .shopping_access import visible_shopping_lists
from .shopping_models import ShoppingSession


def _visible_expenses(user, family):
    from expenses.models import Expense
    from expenses.permissions import finance_queryset

    return finance_queryset(Expense.objects.filter(family=family), user)


def _session_deep_link(session):
    base = f"/?page=shopping&list={session.shopping_list_id}&mode=store"
    if session.status == ShoppingSession.Status.COMPLETED:
        return f"{base}&session={session.id}"
    return base


def install_shopping_context_access():
    """Install object-level Shopping adapters and checkout-to-expense context links.

    ContextRegistry intentionally rejects duplicate public registrations. Until
    it exposes a replace hook, the owning Family app adjusts canonical adapters
    in one place during app startup.
    """
    registry = default_context_registry()
    registry._types["shopping_list"] = ContextTypeAdapter(
        key="shopping_list",
        visible_queryset=lambda user, family: visible_shopping_lists(user).filter(family=family),
        family_id=lambda obj: obj.family_id,
        deep_link=lambda obj: f"/?page=shopping&list={obj.id}",
        lifecycle=lambda obj: "archived" if obj.archived else "available",
    )
    registry._types["shopping_item"] = ContextTypeAdapter(
        key="shopping_item",
        visible_queryset=lambda user, family: ShoppingItem.objects.filter(
            shopping_list__in=visible_shopping_lists(user).filter(family=family)
        ).exclude(hidden_from_user=user).select_related("shopping_list"),
        family_id=lambda obj: obj.shopping_list.family_id,
        deep_link=lambda obj: f"/?page=shopping&item={obj.id}",
    )
    registry._types["shopping_session"] = ContextTypeAdapter(
        key="shopping_session",
        visible_queryset=lambda user, family: ShoppingSession.objects.filter(
            shopping_list__in=visible_shopping_lists(user).filter(family=family)
        ).select_related("shopping_list"),
        family_id=lambda obj: obj.family_id,
        deep_link=_session_deep_link,
        lifecycle=lambda obj: "completed" if obj.status == ShoppingSession.Status.COMPLETED else "available",
    )
    registry._types["expense"] = ContextTypeAdapter(
        key="expense",
        visible_queryset=_visible_expenses,
        family_id=lambda obj: obj.family_id,
        deep_link=lambda obj: f"/?page=expenses&expense={obj.id}",
    )
    context_relation = registry._relations["context"]
    registry._relations["context"] = ContextRelationAdapter(
        key="context",
        allowed_pairs=frozenset(set(context_relation.allowed_pairs) | {("expense", "shopping_session")}),
        can_create=context_relation.can_create,
    )
