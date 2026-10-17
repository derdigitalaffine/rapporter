from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .models import ShoppingList
from .shopping_access import can_access_shopping_list
from .shopping_models import ShoppingSession, ShoppingSessionActivity, ShoppingSessionParticipant


PRESENCE_WRITE_INTERVAL = timedelta(seconds=15)


def start_or_join_shopping_session(shopping_list, user):
    """Start or join the single active session for a list.

    Locking the ShoppingList serializes concurrent starts without introducing a
    second coordination core. The partial unique constraint remains the final
    database invariant.
    """
    if not can_access_shopping_list(user, shopping_list):
        return None, False
    now = timezone.now()
    with transaction.atomic():
        locked_list = ShoppingList.objects.select_for_update().select_related("family").get(pk=shopping_list.pk)
        if not can_access_shopping_list(user, locked_list):
            return None, False
        session = (
            ShoppingSession.objects.select_for_update()
            .filter(shopping_list=locked_list, status=ShoppingSession.Status.ACTIVE)
            .first()
        )
        created = False
        if not session:
            session = ShoppingSession.objects.create(
                family=locked_list.family,
                shopping_list=locked_list,
                started_by=user,
                started_at=now,
                last_activity_at=now,
            )
            created = True
        ShoppingSessionParticipant.objects.update_or_create(
            session=session,
            user=user,
            defaults={"last_seen_at": now},
        )
        if not created:
            ShoppingSession.objects.filter(pk=session.pk).update(last_activity_at=now)
            session.last_activity_at = now
        return session, created


def touch_shopping_session_participant(session, user):
    if not user or not getattr(user, "is_authenticated", False):
        return
    now = timezone.now()
    participant, created = ShoppingSessionParticipant.objects.get_or_create(
        session=session,
        user=user,
        defaults={"last_seen_at": now},
    )
    if not created and participant.last_seen_at < now - PRESENCE_WRITE_INTERVAL:
        ShoppingSessionParticipant.objects.filter(pk=participant.pk).update(last_seen_at=now)


def active_shopping_session(shopping_list):
    return (
        ShoppingSession.objects.filter(
            shopping_list=shopping_list,
            status=ShoppingSession.Status.ACTIVE,
        )
        .select_related("family", "shopping_list", "started_by")
        .first()
    )


def _activity_metadata(client_activity):
    value = client_activity if isinstance(client_activity, dict) else {}
    stream = str(value.get("stream") or "").strip()[:128]
    try:
        sequence = int(value.get("sequence"))
        if sequence < 1:
            sequence = None
    except (TypeError, ValueError):
        sequence = None
    if not stream or sequence is None:
        stream, sequence = "", None
    mutation_id = value.get("mutation_id")
    try:
        mutation_id = UUID(str(mutation_id)) if mutation_id else None
    except (TypeError, ValueError, AttributeError):
        mutation_id = None
    return stream, sequence, mutation_id


def record_shopping_item_activity(item, kind, actor, client_activity=None):
    """Append one ACL-safe activity to an active ShoppingSession.

    ``sequence`` remains a server cursor for collaboration. Learned ordering may
    only consume the explicit client-local stream/sequence pair. A stream pair or
    mutation id is idempotent under offline retry/replay while legacy callers keep
    producing activities that are deliberately excluded from learning.
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return None
    if item.birthday_context or item.hidden_from_user_id:
        return None
    if not can_access_shopping_list(actor, item.shopping_list):
        return None
    client_stream, client_sequence, mutation_id = _activity_metadata(client_activity)
    now = timezone.now()
    with transaction.atomic():
        session = (
            ShoppingSession.objects.select_for_update()
            .filter(
                shopping_list=item.shopping_list,
                status=ShoppingSession.Status.ACTIVE,
            )
            .first()
        )
        if not session:
            return None
        duplicate = None
        if mutation_id:
            duplicate = session.activities.filter(mutation_id=mutation_id).first()
        if duplicate is None and client_stream and client_sequence is not None:
            duplicate = session.activities.filter(
                client_stream=client_stream,
                client_sequence=client_sequence,
            ).first()
        if duplicate:
            return duplicate
        session.activity_seq += 1
        session.last_activity_at = now
        session.save(update_fields=["activity_seq", "last_activity_at", "updated_at"])
        ShoppingSessionParticipant.objects.update_or_create(
            session=session,
            user=actor,
            defaults={"last_seen_at": now},
        )
        return ShoppingSessionActivity.objects.create(
            session=session,
            sequence=session.activity_seq,
            kind=kind,
            item_id=item.id,
            item_name=item.name,
            actor=actor,
            client_stream=client_stream,
            client_sequence=client_sequence,
            mutation_id=mutation_id,
        )
