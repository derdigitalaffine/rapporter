from django.db import transaction

from .models_features import NotificationBadgeState

MAX_BADGE_COUNT = 999


def badge_count(user):
    state = NotificationBadgeState.objects.filter(user=user).only("unread_count").first()
    return state.unread_count if state else 0


def increment_badge(user, amount=1):
    amount = max(0, int(amount or 0))
    with transaction.atomic():
        state, _ = NotificationBadgeState.objects.select_for_update().get_or_create(user=user)
        state.unread_count = min(MAX_BADGE_COUNT, state.unread_count + amount)
        state.save(update_fields=["unread_count", "updated_at"])
        return state.unread_count


def clear_badge(user):
    NotificationBadgeState.objects.filter(user=user).exclude(unread_count=0).update(unread_count=0)
    return 0
