from .context_links import ContextTypeAdapter, default_context_registry
from .models import ShoppingItem
from .shopping_access import visible_shopping_lists


def install_shopping_context_access():
    """Tighten existing Shopping context adapters to object-level list ACL.

    ContextRegistry intentionally rejects duplicate public registrations. Until
    it exposes a replace hook, the owning Family app adjusts the two canonical
    Shopping adapters in one place during app startup.
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
