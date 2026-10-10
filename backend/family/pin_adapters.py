import uuid
from collections import defaultdict

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from .models import BoardPost, FamilyEvent, Note, Routine, ShoppingItem, ShoppingList, Task


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

    def can_pin(self, user, family_id, target_id):
        return self.can_view(user, family_id, target_id)

    def lifecycle_state(self, target):
        return 'available' if target is not None else 'unavailable'

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
        return {
            post.id: self.preview(by_key[(post.family_id, post.target_id)])
            for post in posts
            if (post.family_id, post.target_id) in by_key
        }


class CalendarEventPinAdapter(PinAdapter):
    key = BoardPost.Kind.EVENT

    def queryset(self, user):
        return FamilyEvent.objects.all()

    def preview(self, row):
        return {
            'id': str(row.id),
            'kind': 'event',
            'title': row.title,
            'subtitle': row.starts_at,
            'event_type': row.type,
            'url': f'/?page=calendar&event={row.id}',
        }


class TaskPinAdapter(PinAdapter):
    key = BoardPost.Kind.TASK

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
    key = BoardPost.Kind.ROUTINE

    def queryset(self, user):
        # Keep inactive routines resolvable for an existing pin so the board can
        # render an explicit archived lifecycle instead of leaking a stale snapshot.
        return Routine.objects.all()

    def can_pin(self, user, family_id, target_id):
        return self.queryset(user).filter(id=target_id, family_id=family_id, active=True).exists()

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
    key = BoardPost.Kind.NOTE_REF

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


class ShoppingItemPinAdapter(PinAdapter):
    key = BoardPost.Kind.SHOPPING
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
    key = BoardPost.Kind.SHOPPING_LIST

    def queryset(self, user):
        # Archived lists remain resolvable for existing pins but cannot be newly pinned.
        return ShoppingList.objects.all()

    def can_pin(self, user, family_id, target_id):
        return self.queryset(user).filter(id=target_id, family_id=family_id, archived=False).exists()

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
):
    register_pin_adapter(adapter)


REFERENCE_KINDS = frozenset(PIN_ADAPTERS)


def get_pin_adapter(kind):
    return PIN_ADAPTERS.get(kind)


def unavailable_target(post):
    return {'id': str(post.target_id), 'kind': post.kind, 'available': False}


def resolve_pin_targets(posts, user):
    """Resolve a board page with at most one target query per adapter type."""
    posts = list(posts)
    result = {
        post.id: (None if not post.target_id else unavailable_target(post))
        for post in posts
    }
    grouped = defaultdict(list)
    for post in posts:
        adapter = get_pin_adapter(post.kind)
        if adapter and post.target_id:
            grouped[adapter.key].append(post)

    for key, adapter_posts in grouped.items():
        result.update(PIN_ADAPTERS[key].resolve_many(adapter_posts, user))
    return result


def resolve_pin_target(post, user):
    return resolve_pin_targets([post], user)[post.id]


def validate_pin_target(kind, target_id, family_id, user):
    adapter = get_pin_adapter(kind)
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
