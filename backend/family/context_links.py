from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
import uuid

from django.db.models import Q

from .context_models import ContextLink
from .models import Family, Membership


class ContextLinkError(Exception):
    pass


class InvalidContextReference(ContextLinkError):
    pass


class UnsupportedContextType(ContextLinkError):
    pass


class UnsupportedContextRelation(ContextLinkError):
    pass


class ContextObjectUnavailable(ContextLinkError):
    """Neutral missing/inaccessible result; callers must not distinguish why."""


class ContextLinkPermissionDenied(ContextLinkError):
    pass


@dataclass(frozen=True)
class ContextRef:
    type: str
    id: uuid.UUID

    @classmethod
    def parse(cls, type_key, object_id):
        key = str(type_key or "").strip()
        if not key:
            raise InvalidContextReference("invalid_context_type")
        try:
            parsed_id = object_id if isinstance(object_id, uuid.UUID) else uuid.UUID(str(object_id))
        except (TypeError, ValueError, AttributeError):
            raise InvalidContextReference("invalid_context_id") from None
        return cls(key, parsed_id)


@dataclass(frozen=True)
class ResolvedContextObject:
    ref: ContextRef
    object: object
    lifecycle: str
    deep_link: str


@dataclass(frozen=True)
class ContextTypeAdapter:
    key: str
    visible_queryset: object
    family_id: object
    deep_link: object
    lifecycle: object = lambda obj: "available"
    can_link: object = lambda user, obj: True


@dataclass(frozen=True)
class ContextRelationAdapter:
    key: str
    allowed_pairs: frozenset
    can_create: object = lambda membership, source, context: membership.role != Membership.Role.GUEST

    def allows(self, source_type, context_type):
        return (source_type, context_type) in self.allowed_pairs


@dataclass(frozen=True)
class VisibleContextLink:
    link: ContextLink
    source: ResolvedContextObject
    context: ResolvedContextObject


class ContextRegistry:
    def __init__(self):
        self._types = {}
        self._relations = {}

    def register_type(self, adapter):
        if not adapter.key or adapter.key in self._types:
            raise ValueError(f"duplicate context type: {adapter.key}")
        self._types[adapter.key] = adapter
        return adapter

    def register_relation(self, adapter):
        if not adapter.key or adapter.key in self._relations:
            raise ValueError(f"duplicate context relation: {adapter.key}")
        self._relations[adapter.key] = adapter
        return adapter

    def type_adapter(self, key):
        try:
            return self._types[key]
        except KeyError:
            raise UnsupportedContextType(key) from None

    def relation_adapter(self, key):
        try:
            return self._relations[key]
        except KeyError:
            raise UnsupportedContextRelation(key) from None

    def resolve_many(self, user, family, refs, *, strict=True):
        """Resolve visible refs with at most one domain query per registered type."""
        grouped = defaultdict(set)
        adapters = {}
        normalized = []
        for ref in refs:
            normalized_ref = ref if isinstance(ref, ContextRef) else ContextRef.parse(ref[0], ref[1])
            normalized.append(normalized_ref)
            try:
                adapter = self.type_adapter(normalized_ref.type)
            except UnsupportedContextType:
                if strict:
                    raise
                continue
            adapters[normalized_ref.type] = adapter
            grouped[normalized_ref.type].add(normalized_ref.id)

        resolved = {}
        for type_key, ids in grouped.items():
            adapter = adapters[type_key]
            for obj in adapter.visible_queryset(user, family).filter(pk__in=ids):
                if adapter.family_id(obj) != family.id:
                    continue
                ref = ContextRef(type_key, obj.pk)
                resolved[ref] = ResolvedContextObject(
                    ref=ref,
                    object=obj,
                    lifecycle=adapter.lifecycle(obj),
                    deep_link=adapter.deep_link(obj),
                )
        return {ref: resolved[ref] for ref in normalized if ref in resolved}


def _active_membership(user, family):
    membership = Membership.objects.filter(
        user=user,
        family=family,
        family__status=Family.Status.ACTIVE,
    ).first()
    if not membership:
        raise ContextLinkPermissionDenied("family_unavailable")
    return membership


def _parse_link_id(link_id):
    try:
        return link_id if isinstance(link_id, uuid.UUID) else uuid.UUID(str(link_id))
    except (TypeError, ValueError, AttributeError):
        raise ContextObjectUnavailable("context_link_unavailable") from None


def create_context_link(
    *,
    user,
    family,
    source_type,
    source_id,
    context_type,
    context_id,
    relation_key="context",
    registry=None,
):
    """Create an idempotent link only while both objects are currently visible."""
    membership = _active_membership(user, family)
    registry = registry or default_context_registry()
    source_ref = ContextRef.parse(source_type, source_id)
    context_ref = ContextRef.parse(context_type, context_id)
    # Validate both endpoint types before the pair so unknown client-provided
    # model keys cannot be reinterpreted as a relation error.
    source_adapter = registry.type_adapter(source_ref.type)
    registry.type_adapter(context_ref.type)
    relation = registry.relation_adapter(relation_key)
    if not relation.allows(source_ref.type, context_ref.type):
        raise UnsupportedContextRelation(f"{relation_key}:{source_ref.type}->{context_ref.type}")

    resolved = registry.resolve_many(user, family, [source_ref, context_ref])
    if source_ref not in resolved or context_ref not in resolved:
        raise ContextObjectUnavailable("context_object_unavailable")
    source_obj = resolved[source_ref].object
    context_obj = resolved[context_ref].object
    if not source_adapter.can_link(user, source_obj):
        raise ContextLinkPermissionDenied("source_read_only")
    if not relation.can_create(membership, source_obj, context_obj):
        raise ContextLinkPermissionDenied("relation_not_allowed")

    return ContextLink.objects.get_or_create(
        family=family,
        source_type=source_ref.type,
        source_id=source_ref.id,
        context_type=context_ref.type,
        context_id=context_ref.id,
        relation_key=relation.key,
        defaults={"created_by": user},
    )


def list_context_links(*, user, family, anchor_type, anchor_id, limit=50, registry=None):
    """Return only links whose two endpoints are still visible to the caller."""
    _active_membership(user, family)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise InvalidContextReference("invalid_limit")
    registry = registry or default_context_registry()
    anchor = ContextRef.parse(anchor_type, anchor_id)
    anchor_resolved = registry.resolve_many(user, family, [anchor])
    if anchor not in anchor_resolved:
        raise ContextObjectUnavailable("context_object_unavailable")

    scan_limit = min(limit * 4, 400)
    rows = list(
        ContextLink.objects.filter(family=family)
        .filter(
            Q(source_type=anchor.type, source_id=anchor.id)
            | Q(context_type=anchor.type, context_id=anchor.id)
        )
        .order_by("created_at", "id")[:scan_limit]
    )
    counterparts = []
    for row in rows:
        source = ContextRef(row.source_type, row.source_id)
        context = ContextRef(row.context_type, row.context_id)
        if source != anchor:
            counterparts.append(source)
        if context != anchor:
            counterparts.append(context)

    resolved = {anchor: anchor_resolved[anchor]}
    resolved.update(registry.resolve_many(user, family, counterparts, strict=False))
    visible = []
    for row in rows:
        source = ContextRef(row.source_type, row.source_id)
        context = ContextRef(row.context_type, row.context_id)
        if source not in resolved or context not in resolved:
            continue
        visible.append(VisibleContextLink(row, resolved[source], resolved[context]))
        if len(visible) == limit:
            break
    return visible


def remove_context_link(*, user, family, link_id, registry=None):
    """Remove metadata without touching either domain object.

    Only the source must still be visible and link-manageable. This deliberately
    permits cleanup of a link whose context was deleted or whose ACL was revoked.
    """
    membership = _active_membership(user, family)
    if membership.role == Membership.Role.GUEST:
        raise ContextLinkPermissionDenied("relation_not_allowed")
    link = ContextLink.objects.filter(family=family, id=_parse_link_id(link_id)).first()
    if not link:
        raise ContextObjectUnavailable("context_link_unavailable")
    registry = registry or default_context_registry()
    source = ContextRef(link.source_type, link.source_id)
    resolved = registry.resolve_many(user, family, [source], strict=False)
    if source not in resolved:
        raise ContextObjectUnavailable("context_link_unavailable")
    try:
        source_adapter = registry.type_adapter(source.type)
    except UnsupportedContextType:
        raise ContextObjectUnavailable("context_link_unavailable") from None
    if not source_adapter.can_link(user, resolved[source].object):
        raise ContextLinkPermissionDenied("source_read_only")
    link.delete()


def _trip_lifecycle(trip):
    return "archived" if trip.archived else "available"


def _note_can_link(user, note):
    return note.author_id == user.id or note.shares.filter(user=user, permission="edit").exists()


@lru_cache(maxsize=1)
def default_context_registry():
    """Canonical registry. New domains extend this allowlist explicitly."""
    from .board_models import BoardPost
    from .models import Task
    from .notes_models import Note
    from .travel_models import Trip

    registry = ContextRegistry()
    registry.register_type(
        ContextTypeAdapter(
            key="task",
            visible_queryset=lambda user, family: Task.objects.filter(family=family).exclude(hidden_from_user=user),
            family_id=lambda obj: obj.family_id,
            deep_link=lambda obj: f"/?page=tasks&task={obj.id}",
        )
    )
    registry.register_type(
        ContextTypeAdapter(
            key="note",
            visible_queryset=lambda user, family: Note.objects.filter(family=family)
            .filter(Q(author=user) | Q(shares__user=user))
            .distinct(),
            family_id=lambda obj: obj.family_id,
            deep_link=lambda obj: f"/?page=notes&note={obj.id}",
            can_link=_note_can_link,
        )
    )
    registry.register_type(
        ContextTypeAdapter(
            key="trip",
            visible_queryset=lambda user, family: Trip.objects.filter(family=family),
            family_id=lambda obj: obj.family_id,
            deep_link=lambda obj: "/?page=trips",
            lifecycle=_trip_lifecycle,
        )
    )
    registry.register_type(
        ContextTypeAdapter(
            key="board_post",
            visible_queryset=lambda user, family: BoardPost.objects.filter(family=family),
            family_id=lambda obj: obj.family_id,
            deep_link=lambda obj: f"/?page=board&post={obj.id}&family={obj.family_id}",
        )
    )
    registry.register_relation(
        ContextRelationAdapter(
            key="context",
            allowed_pairs=frozenset(
                {
                    ("task", "trip"),
                    ("note", "trip"),
                    ("board_post", "trip"),
                }
            ),
        )
    )
    return registry
