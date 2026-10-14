from django.db import transaction
from django.utils import timezone

from .models import ShoppingList
from .shopping_access import can_access_shopping_list
from .shopping_models import ShoppingSession, ShoppingSessionActivity, ShoppingSessionParticipant


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
    ShoppingSessionParticipant.objects.update_or_create(
        session=session,
        user=user,
        defaults={"last_seen_at": timezone.now()},
    )


def active_shopping_session(shopping_list):
    return (
        ShoppingSession.objects.filter(
            shopping_list=shopping_list,
            status=ShoppingSession.Status.ACTIVE,
        )
        .select_related("family", "shopping_list", "started_by")
        .first()
    )


def record_shopping_item_activity(item, kind, actor):
    """Append one ACL-safe activity to an active ShoppingSession.

    Gift/hidden rows are deliberately excluded so an activity stream can never
    become a side channel around ShoppingItem visibility.
    """
    if not actor or not getattr(actor, "is_authenticated", False):
        return None
    if item.birthday_context or item.hidden_from_user_id:
        return None
    if not can_access_shopping_list(actor, item.shopping_list):
        return None
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
        )