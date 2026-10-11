from family.context_links import (
    ContextRelationAdapter,
    ContextTypeAdapter,
    UnsupportedContextRelation,
    UnsupportedContextType,
    default_context_registry,
)


def register_context_adapters():
    """Extend the canonical ContextLink allowlist without modifying its core."""
    from documents.access import can_manage_document, visible_documents

    registry = default_context_registry()
    try:
        registry.type_adapter("document")
    except UnsupportedContextType:
        registry.register_type(
            ContextTypeAdapter(
                key="document",
                visible_queryset=lambda user, family: visible_documents(user, family.id),
                family_id=lambda obj: obj.family_id,
                deep_link=lambda obj: f"/api/documents/{obj.id}/file/",
                lifecycle=lambda obj: "archived" if obj.archived_at else "available",
                can_link=can_manage_document,
            )
        )
    try:
        registry.relation_adapter("correspondence.action")
    except UnsupportedContextRelation:
        registry.register_relation(
            ContextRelationAdapter(
                key="correspondence.action",
                allowed_pairs=frozenset({("document", "shopping_item")}),
            )
        )
