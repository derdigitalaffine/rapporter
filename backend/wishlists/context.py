from family.context_links import (
    ContextRelationAdapter,
    ContextTypeAdapter,
    UnsupportedContextRelation,
    UnsupportedContextType,
    default_context_registry,
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


def register_context_adapters():
    from expenses.models import Expense
    from .access import can_coordinate_item, can_manage_wishlist, visible_items, visible_wishlists

    registry = default_context_registry()
    _register_type(
        registry,
        ContextTypeAdapter(
            key="wishlist",
            visible_queryset=lambda user, family: visible_wishlists(user, family.id, include_inactive=True),
            family_id=lambda obj: obj.family_id,
            deep_link=lambda obj: f"/?page=wishlists&wishlist={obj.id}",
            lifecycle=lambda obj: "available" if obj.active else "archived",
            can_link=can_manage_wishlist,
        ),
    )
    _register_type(
        registry,
        ContextTypeAdapter(
            key="wishlist_item",
            visible_queryset=lambda user, family: visible_items(user, family.id, include_archived=True),
            family_id=lambda obj: obj.wishlist.family_id,
            deep_link=lambda obj: f"/?page=wishlists&wishlist={obj.wishlist_id}&item={obj.id}",
            lifecycle=lambda obj: "archived" if obj.archived_at else "available",
            can_link=can_coordinate_item,
        ),
    )
    _register_type(
        registry,
        ContextTypeAdapter(
            key="expense",
            visible_queryset=lambda user, family: Expense.objects.filter(
                family=family,
                family__memberships__user=user,
                status=Expense.Status.POSTED,
            ).distinct(),
            family_id=lambda obj: obj.family_id,
            deep_link=lambda obj: f"/?page=expenses&expense={obj.id}",
        ),
    )
    _register_relation(
        registry,
        ContextRelationAdapter(
            key="wishlist.action",
            allowed_pairs=frozenset(
                {
                    ("wishlist_item", "task"),
                    ("wishlist_item", "shopping_item"),
                    ("wishlist_item", "expense"),
                }
            ),
        ),
    )
    _register_relation(
        registry,
        ContextRelationAdapter(
            key="birthday.wishlist",
            allowed_pairs=frozenset({("wishlist", "birthday_occasion")}),
        ),
    )
