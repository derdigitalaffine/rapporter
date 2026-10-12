import uuid
from collections import defaultdict
from datetime import date

from django.db.models import CharField, Q, Value
from rest_framework.exceptions import ValidationError

from .context_links import ContextRef, default_context_registry
from .models import BoardPost, FamilyEvent, Note, Routine, ShoppingItem, ShoppingList, Task


LEGACY_KIND_TO_ADAPTER_KEY = {
    BoardPost.Kind.EVENT: 'calendar_event',
    BoardPost.Kind.TASK: 'task',
    BoardPost.Kind.NOTE_REF: 'note',
    BoardPost.Kind.SHOPPING: 'shopping_item',
    BoardPost.Kind.ROUTINE: 'routine',
    BoardPost.Kind.SHOPPING_LIST: 'shopping_list',
    BoardPost.Kind.TRIP: 'trip',
    BoardPost.Kind.DOCUMENT: 'document',
}
ADAPTER_KEY_TO_LEGACY_KIND = {value: key for key, value in LEGACY_KIND_TO_ADAPTER_KEY.items()}
CANONICAL_ADAPTER_KEYS = frozenset(ADAPTER_KEY_TO_LEGACY_KIND)


def canonical_adapter_key(*, adapter_key='', legacy_kind=''):
    """Return a stable adapter key without confusing native board notes with note refs."""
    key = str(adapter_key or '').strip()
    if key:
        return key if key in CANONICAL_ADAPTER_KEYS else ''
    return LEGACY_KIND_TO_ADAPTER_KEY.get(legacy_kind, '')


def legacy_kind_for_adapter_key(adapter_key):
    return ADAPTER_KEY_TO_LEGACY_KIND.get(str(adapter_key or '').strip())


class PinAdapter:
    """Allow-listed resolver for one canonical FamilyOS object type.

    Adapters own target visibility and preview projection. Board pins only keep the
    canonical object's id; every read re-authorizes the target through this layer.
    """

    key = None
    family_lookup = 'family_id'

    def queryset(self, user):
        raise NotImplementedError

    def preview(self, target):
        raise NotImplementedError

    def target_family_id(self, target):
        return target.family_id

    def can_view(self, user, family_id, target_id):
        return self.queryset(user).filter(
            id=target_id,
            **{self.family_lookup: family_id},
        ).exists()

    def pinnable_queryset(self, user, family_id):
        """Canonical source admission for both creation and picker pagination."""
        return self.queryset(user).filter(**{self.family_lookup: family_id})

    def can_pin(self, user, family_id, target_id):
        return self.pinnable_queryset(user, family_id).filter(pk=target_id).exists()

    def lifecycle_state(self, target):
        return 'available' if target is not None else 'unavailable'

    def decorate_preview(self, preview, target, user):
        """Attach non-ACL-widening source capabilities to an authorized preview."""
        return preview

    def audience_queryset(self, posts, user):
        return self.queryset(user).filter(
            id__in={post.target_id for post in posts},
            **{f'{self.family_lookup}__in': {post.family_id for post in posts}},
        )

    def resolve_many_with_audiences(self, posts, user, memberships):
        """Resolve previews and effective audiences in one canonical target query.

        Each UNION branch uses the adapter's existing authorization queryset.
        No source ACL is copied into Pinboard, and query count stays independent
        of the number of pins on the page.
        """
        posts = list(posts)
        by_key = defaultdict(list)
        for post in posts:
            by_key[(post.family_id, post.target_id)].append(post)
        members = {str(member.pk): member for member in memberships}
        branches = []
        for member in memberships:
            scoped_posts = [post for post in posts if post.family_id == member.family_id]
            if scoped_posts:
                branches.append(self.audience_queryset(scoped_posts, member.user).order_by().annotate(
                    _pin_member_id=Value(str(member.pk), output_field=CharField()),
                ))
        previews, audiences = {}, defaultdict(set)
        if not branches:
            return previews, audiences
        rows = branches[0].union(*branches[1:], all=True) if len(branches) > 1 else branches[0]
        for target in rows:
            member = members[target._pin_member_id]
            for post in by_key.get((self.target_family_id(target), target.pk), []):
                from .pin_visibility import pin_scope_for_membership
                if pin_scope_for_membership(post, member):
                    audiences[post.pk].add(member.pk)
                    if member.user_id == user.pk:
                        previews[post.pk] = self.decorate_preview(self.preview(target), target, user)
        return previews, audiences

    def resolve_many(self, posts, user):
        posts = [post for post in posts if post.target_id]
        if not posts:
            return {}

        target_ids = {post.target_id for post in posts}
        family_ids = {post.family_id for post in posts}
        rows = self.queryset(user).filter(
            id__in=target_ids,
            **{f'{self.family_lookup}__in': family_ids},
        )
        by_key = {(self.target_family_id(row), row.id): row for row in rows}
        result = {}
        for post in posts:
            target = by_key.get((post.family_id, post.target_id))
            if target is None:
                continue
            result[post.id] = self.decorate_preview(self.preview(target), target, user)
        return result


class ContextBackedPinAdapter(PinAdapter):
    """Board projection backed by the canonical ContextRef visibility contract."""

    context_type = None

    @property
    def context_adapter(self):
        return default_context_registry().type_adapter(self.context_type)

    def queryset(self, user):
        raise RuntimeError('Context-backed pin adapters require a family scope.')

    def can_view(self, user, family_id, target_id):
        ref = ContextRef.parse(self.context_type, target_id)
        return self.context_adapter.visible_queryset(user, family_id).filter(pk=ref.id).exists()

    def pinnable_queryset(self, user, family_id):
        return self.context_adapter.visible_queryset(user, family_id)

    def target_family_id(self, target):
        return self.context_adapter.family_id(target)

    def lifecycle_state(self, target):
        return self.context_adapter.lifecycle(target)

    def deep_link(self, target):
        return self.context_adapter.deep_link(target)

    def audience_queryset(self, posts, user):
        rows = None
        for family_id in {post.family_id for post in posts}:
            target_ids = {post.target_id for post in posts if post.family_id == family_id}
            scoped = self.context_adapter.visible_queryset(user, family_id).filter(pk__in=target_ids)
            rows = scoped if rows is None else rows | scoped
        return rows.distinct()

    def resolve_many(self, posts, user):
        posts = [post for post in posts if post.target_id]
        if not posts:
            return {}

        target_ids_by_family = defaultdict(set)
        for post in posts:
            ref = ContextRef.parse(self.context_type, post.target_id)
            target_ids_by_family[post.family_id].add(ref.id)

        rows = None
        for family_id, target_ids in target_ids_by_family.items():
            scoped = self.context_adapter.visible_queryset(user, family_id).filter(pk__in=target_ids)
            rows = scoped if rows is None else rows | scoped
        rows = rows.distinct()
        by_key = {(self.target_family_id(row), row.id): row for row in rows}
        result = {}
        for post in posts:
            target = by_key.get((post.family_id, post.target_id))
            if target is None:
                continue
            result[post.id] = self.decorate_preview(self.preview(target), target, user)
        return result


class CalendarEventPinAdapter(PinAdapter):
    key = 'calendar_event'

    def queryset(self, user):
        return FamilyEvent.objects.all()

    def preview(self, row):
        payload = row.payload if isinstance(row.payload, dict) else {}
        dates = {}
        for key in ('date_start', 'date_end_exclusive'):
            value = payload.get(key)
            if isinstance(value, str):
                try:
                    dates[key] = date.fromisoformat(value).isoformat()
                except ValueError:
                    pass
        return {
            'id': str(row.id),
            'kind': 'event',
            'title': row.title,
            'subtitle': row.starts_at,
            'event_type': row.type,
            'ends_at': row.ends_at,
            **dates,
            'url': f'/?page=calendar&event={row.id}',
        }


class TaskPinAdapter(PinAdapter):
    key = 'task'

    def queryset(self, user):
        return Task.objects.exclude(hidden_from_user=user)

    def preview(self, row):
        return {
            'id': str(row.id),
            'kind': 'task',
            'title': row.title,
            'subtitle': row.due_at,
            'completed': bool(row.completed_at),
            'url': f'/?page=tasks&task={row.id}',
        }


class RoutinePinAdapter(PinAdapter):
    key = 'routine'

    def queryset(self, user):
        # Keep inactive routines resolvable for an existing pin so the board can
        # render an explicit archived lifecycle instead of leaking a stale snapshot.
        return Routine.objects.all()

    def pinnable_queryset(self, user, family_id):
        return super().pinnable_queryset(user, family_id).filter(active=True)

    def lifecycle_state(self, target):
        return 'available' if target.active else 'archived'

    def preview(self, row):
        return {
            'id': str(row.id),
            'kind': 'routine',
            'title': row.name,
            'subtitle': None,
            'lifecycle': self.lifecycle_state(row),
            'url': f'/?page=tasks&routine={row.id}',
        }


class NotePinAdapter(PinAdapter):
    key = 'note'

    def queryset(self, user):
        return Note.objects.filter(Q(author=user) | Q(shares__user=user)).distinct()

    def preview(self, row):
        preview = (row.body or '').strip().replace('\n', ' ')[:180]
        return {
            'id': str(row.id),
            'kind': 'note_ref',
            'title': row.title or 'Notiz',
            'subtitle': preview,
            'url': f'/?page=notes&note={row.id}',
        }

    def decorate_preview(self, preview, row, user):
        if row.author_id == user.id:
            return {
                **preview,
                'can_share_source': True,
                'source_share_url': f'/?page=notes&note={row.id}&share=1',
            }
        return preview


class ShoppingItemPinAdapter(PinAdapter):
    key = 'shopping_item'
    family_lookup = 'shopping_list__family_id'

    def queryset(self, user):
        # Match the canonical ShoppingItem API: hidden gift items stay private.
        return ShoppingItem.objects.exclude(hidden_from_user=user).select_related('shopping_list')

    def target_family_id(self, target):
        return target.shopping_list.family_id

    def preview(self, row):
        return {
            'id': str(row.id),
            'kind': 'shopping',
            'title': row.name,
            'subtitle': row.shopping_list.name,
            'checked': row.checked,
            'url': '/?page=shopping',
        }


class ShoppingListPinAdapter(PinAdapter):
    key = 'shopping_list'

    def queryset(self, user):
        # Archived lists remain resolvable for existing pins but cannot be newly pinned.
        return ShoppingList.objects.all()

    def pinnable_queryset(self, user, family_id):
        return super().pinnable_queryset(user, family_id).filter(archived=False)

    def lifecycle_state(self, target):
        return 'archived' if target.archived else 'available'

    def preview(self, row):
        return {
            'id': str(row.id),
            'kind': 'shopping_list',
            'title': row.name,
            'subtitle': row.store or None,
            'lifecycle': self.lifecycle_state(row),
            'url': f'/?page=shopping&list={row.id}',
        }


class TripPinAdapter(ContextBackedPinAdapter):
    key = 'trip'
    context_type = 'trip'

    def preview(self, row):
        return {
            'id': str(row.id),
            'kind': 'trip',
            'title': row.title,
            'subtitle': row.destination,
            'starts_on': row.starts_on.isoformat(),
            'ends_on': row.ends_on.isoformat(),
            'lifecycle': self.lifecycle_state(row),
            'url': self.deep_link(row),
        }


class DocumentPinAdapter(PinAdapter):
    key = 'document'

    def queryset(self, user):
        raise RuntimeError('Document pin adapters require a family scope.')

    def _visible(self, user, family_ids, *, include_archived=False):
        # Import lazily so the Documents domain remains the sole owner of its ACL
        # without introducing a family.models <-> documents.access import cycle.
        from documents.access import visible_documents_for_user

        return visible_documents_for_user(
            user,
            family_ids,
            include_archived=include_archived,
            include_domain_managed=False,
        )

    def can_view(self, user, family_id, target_id):
        return self._visible(user, [family_id], include_archived=True).filter(pk=target_id).exists()

    def pinnable_queryset(self, user, family_id):
        return self._visible(user, [family_id])

    def audience_queryset(self, posts, user):
        return self._visible(user, {post.family_id for post in posts}, include_archived=True).filter(
            pk__in={post.target_id for post in posts},
        )

    def lifecycle_state(self, target):
        return 'archived' if target.archived_at else 'available'

    def preview(self, row):
        subtitle = row.correspondent or (row.document_date.isoformat() if row.document_date else None)
        return {
            'id': str(row.id),
            'kind': 'document',
            'title': row.title,
            'subtitle': subtitle,
            'lifecycle': self.lifecycle_state(row),
            'url': f'/api/documents/{row.id}/file/',
        }

    def resolve_many(self, posts, user):
        posts = [post for post in posts if post.target_id]
        if not posts:
            return {}

        target_ids = {post.target_id for post in posts}
        family_ids = {post.family_id for post in posts}
        rows = self._visible(user, family_ids, include_archived=True).filter(pk__in=target_ids)
        by_key = {(row.family_id, row.id): row for row in rows}
        result = {}
        for post in posts:
            target = by_key.get((post.family_id, post.target_id))
            if target is None:
                continue
            result[post.id] = self.decorate_preview(self.preview(target), target, user)
        return result


PIN_ADAPTERS = {}


def register_pin_adapter(adapter):
    if not adapter.key or adapter.key in PIN_ADAPTERS:
        raise RuntimeError(f'Invalid or duplicate pin adapter key: {adapter.key!r}')
    PIN_ADAPTERS[adapter.key] = adapter
    return adapter


for adapter in (
    CalendarEventPinAdapter(),
    TaskPinAdapter(),
    RoutinePinAdapter(),
    NotePinAdapter(),
    ShoppingItemPinAdapter(),
    ShoppingListPinAdapter(),
    TripPinAdapter(),
    DocumentPinAdapter(),
):
    register_pin_adapter(adapter)


ADAPTER_KEYS = frozenset(PIN_ADAPTERS)
REFERENCE_KINDS = frozenset(LEGACY_KIND_TO_ADAPTER_KEY)


def get_pin_adapter(key):
    key = str(key or '').strip()
    return PIN_ADAPTERS.get(key) or PIN_ADAPTERS.get(LEGACY_KIND_TO_ADAPTER_KEY.get(key, ''))


def adapter_key_for_post(post):
    stored = str(getattr(post, 'adapter_key', '') or '').strip()
    if stored:
        return stored if stored in PIN_ADAPTERS else ''
    return LEGACY_KIND_TO_ADAPTER_KEY.get(post.kind, '')


def unavailable_target(post):
    return {'id': str(post.target_id), 'kind': post.kind, 'available': False}


def resolve_pin_targets(posts, user):
    """Resolve a board page with at most one target query per canonical adapter type."""
    posts = list(posts)
    result = {
        post.id: (None if not post.target_id else unavailable_target(post))
        for post in posts
    }
    grouped = defaultdict(list)
    for post in posts:
        key = adapter_key_for_post(post)
        adapter = PIN_ADAPTERS.get(key)
        if adapter and post.target_id:
            grouped[key].append(post)

    for key, adapter_posts in grouped.items():
        result.update(PIN_ADAPTERS[key].resolve_many(adapter_posts, user))
    return result


def resolve_pin_target(post, user):
    return resolve_pin_targets([post], user)[post.id]


def validate_pin_target(kind, target_id, family_id, user, *, adapter_key=''):
    key = canonical_adapter_key(adapter_key=adapter_key, legacy_kind=kind)
    adapter = PIN_ADAPTERS.get(key)
    if adapter is None:
        if target_id:
            raise ValidationError({'target_id': 'Dieser Pinnwand-Typ darf kein Ziel besitzen.'})
        return
    if not target_id:
        raise ValidationError({'target_id': 'Bitte ein Objekt zum Anpinnen auswählen.'})
    try:
        target_id = uuid.UUID(str(target_id))
    except (TypeError, ValueError, AttributeError):
        raise ValidationError({'target_id': 'Ungültiges Ziel.'})
    if not adapter.can_pin(user, family_id, target_id):
        raise ValidationError({'target_id': 'Das ausgewählte Objekt ist in dieser Familie nicht verfügbar.'})
