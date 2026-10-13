import re
from urllib.parse import urlsplit, urlunsplit

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from family.models_features import NotificationBadgeState

from .models import Notification

_EVENT_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,95}$")


def normalize_resource_url(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if any(ord(char) < 32 for char in raw) or "\\" in raw:
        raise ValueError("invalid_resource_url")
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or raw.startswith("//"):
        raise ValueError("invalid_resource_url")
    path = parsed.path or "/"
    return urlunsplit(("", "", path, parsed.query, ""))


def unread_count(user, *, family=None):
    queryset = Notification.objects.filter(Q(recipient__user=user) | Q(recipient_user=user), read_at__isnull=True)
    if family is not None:
        queryset = queryset.filter(family=family)
    return queryset.count()


def sync_launcher_badge(user):
    count = min(999, unread_count(user))
    NotificationBadgeState.objects.update_or_create(user=user, defaults={"unread_count": count})
    return count


def record_notification(*, recipient, event_type, title, body="", resource_url="", priority=Notification.Priority.NORMAL):
    event_type = str(event_type or "").strip().lower()
    title = str(title or "").strip()
    if not _EVENT_TYPE_RE.fullmatch(event_type):
        raise ValueError("invalid_event_type")
    if not title:
        raise ValueError("title_required")
    if recipient.family_id is None or recipient.user_id is None:
        raise ValueError("recipient_required")
    resource_url = normalize_resource_url(resource_url)
    with transaction.atomic():
        notification = Notification.objects.create(
            family_id=recipient.family_id,
            recipient=recipient,
            event_type=event_type,
            title=title[:180],
            body=str(body or "")[:1000],
            resource_url=resource_url,
            priority=priority if priority in Notification.Priority.values else Notification.Priority.NORMAL,
        )
        count = sync_launcher_badge(recipient.user)
    return notification, count


def set_read(notification, *, read=True):
    target = timezone.now() if read else None
    if bool(notification.read_at) == bool(target):
        return notification
    notification.read_at = target
    notification.save(update_fields=["read_at"])
    sync_launcher_badge(notification.recipient_user or notification.recipient.user)
    return notification


def mark_all_read(*, membership):
    with transaction.atomic():
        updated = Notification.objects.filter(recipient=membership, read_at__isnull=True).update(read_at=timezone.now())
        count = sync_launcher_badge(membership.user)
    return updated, count


def record_personal_notification(*, user, event_type, title, body="", resource_url=""):
    """A user recipient in the same canonical store, with no family grant."""
    event_type = str(event_type or "").strip().lower()
    if not _EVENT_TYPE_RE.fullmatch(event_type) or not str(title or "").strip():
        raise ValueError("invalid_notification")
    with transaction.atomic():
        row = Notification.objects.create(recipient_user=user, event_type=event_type, title=str(title).strip()[:180], body=str(body or "")[:1000], resource_url=normalize_resource_url(resource_url))
        count = sync_launcher_badge(user)
    return row, count
