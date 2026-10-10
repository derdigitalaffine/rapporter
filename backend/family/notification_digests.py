"""Server-owned notification outbox. No browser timers or in-memory deduplication."""
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from .models import Family, Membership, ShoppingItem, ShoppingList
from .models_features import NotificationBatch, NotificationPreference
from .push import send_user_push

IMPORTANT = {"board.created", "task.status_changed", "task.assigned", "inbox.created", "family.member.joined", "family.member.updated", "family.member.removed"}
WINDOW = timedelta(seconds=90)
MAX_EVENTS = 128


def is_quiet(pref, family, now=None):
    if not pref or not pref.quiet_hours_enabled:
        return False
    try:
        zone = ZoneInfo(family.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("Europe/Berlin")
    local = (now or timezone.now()).astimezone(zone).time().replace(tzinfo=None)
    start, end = pref.quiet_start, pref.quiet_end
    return start <= local < end if start < end else local >= start or local < end


def delivery_policy(pref, family, event_type, now=None):
    level = pref.detail_level if pref else "summary"
    if level == "important" and event_type not in IMPORTANT:
        return "drop"
    if is_quiet(pref, family, now) or (level == "summary" and event_type.startswith("shopping.")):
        return "queue"
    return "send"


def enqueue_notification(membership, event_type, context, *, url=None):
    now = timezone.now()
    shopping = event_type.startswith("shopping.")
    resource = str(context.get("list_id", "family")) if shopping else str(context.get("task_id") or context.get("event_id") or context.get("inbox_id") or "family")
    bucket = f"{event_type.split('.')[0]}:{resource}"
    key = str(context.get("item_id") or context.get("task_id") or context.get("event_id") or context.get("inbox_id") or context.get("routine_id") or event_type)
    # A membership row exists before the batch does: lock it to serialize concurrent creates.
    with transaction.atomic():
        Membership.objects.select_for_update().get(pk=membership.pk)
        batch, _ = NotificationBatch.objects.get_or_create(membership=membership, bucket=bucket, defaults={"due_at": now + WINDOW})
        batch = NotificationBatch.objects.select_for_update().get(pk=batch.pk)
        events = batch.events.copy() if not batch.delivered_at else {}
        if not events:
            batch.due_at = now + WINDOW
            batch.attempts = 0
        context = {k: str(v) if v is not None else None for k, v in context.items()}
        prior = events.get(key)
        # Checking and undoing in the same burst cancel, while a new item remains an addition.
        if prior and prior["event_type"] == "shopping.item.completed" and event_type == "shopping.item.reopened":
            events.pop(key, None)
        elif prior and prior["event_type"] == "shopping.item.reopened" and event_type == "shopping.item.completed":
            events.pop(key, None)
        else:
            if prior and prior["event_type"] == "shopping.item.created":
                event_type = "shopping.item.created"
            if key in events or len(events) < MAX_EVENTS:
                events[key] = {"event_type": event_type, "context": context, "url": url, "queued_at": prior.get("queued_at") if prior else now.isoformat()}
            else:
                events["overflow"] = {"event_type": "shopping.item.updated" if shopping else event_type, "context": {"list_id": context.get("list_id"), "list": context.get("list"), "overflow": True}, "url": url, "queued_at": now.isoformat()}
        batch.events = events
        batch.delivered_at = None
        batch.save(update_fields=["events", "due_at", "attempts", "delivered_at", "updated_at"])


def _visible_events(batch, pref):
    from .domain_notifications import EVENT_SPECS, _preference_enabled
    member = batch.membership
    result = []
    for event in batch.events.values():
        kind, ctx = event["event_type"], event["context"]
        spec = EVENT_SPECS.get(kind)
        if not spec or not _preference_enabled(member, spec, {member.id: pref}):
            continue
        if pref and pref.detail_level == "important" and kind not in IMPORTANT:
            continue
        if kind.startswith("shopping.") and ctx.get("list_id"):
            if not ShoppingList.objects.filter(pk=ctx["list_id"], family=member.family).exists():
                continue
            if ctx.get("item_id"):
                item = ShoppingItem.objects.filter(pk=ctx["item_id"], shopping_list__family=member.family).first()
                if not item or getattr(item, "hidden_from_user_id", None) == member.user_id:
                    continue
        if kind.startswith("task.") and ctx.get("task_id"):
            from .models import Task
            task = Task.objects.filter(pk=ctx["task_id"], family=member.family).first()
            if not task or getattr(task, "hidden_from_user_id", None) == member.user_id:
                continue
            if kind == "task.assigned" and task.assignee_id != member.user_id:
                continue
        if kind == "inbox.created" and ctx.get("inbox_id"):
            from .models import InboxItem, InboxReceipt
            item = InboxItem.objects.filter(pk=ctx["inbox_id"], family=member.family, withdrawn_at__isnull=True).first()
            if not item:
                continue
            if item.source == "manual_message":
                receipt = InboxReceipt.objects.filter(item=item, membership=member).first()
                if not receipt or receipt.read_at:
                    continue
        result.append(event)
    return result


def _shopping_event_order(event):
    """PostgreSQL JSONB does not preserve object-key insertion order."""
    queued_at = event.get("queued_at")
    item_id = event.get("context", {}).get("item_id")
    return (queued_at is None, queued_at or "", str(item_id or ""))


def _render(batch, events):
    from .domain_notifications import EVENT_SPECS, _SafeContext, _target_url
    family = batch.membership.family
    lang = "en" if family.locale.startswith("en") else "de"
    if batch.bucket.startswith("shopping:"):
        events = sorted(events, key=_shopping_event_order)
        first = events[0]
        overflow = any(e["context"].get("overflow") for e in events)
        events = [e for e in events if not e["context"].get("overflow")]
        names = list(dict.fromkeys(e["context"].get("item", "") for e in events if e["context"].get("item")))
        list_name = first["context"].get("list", "Einkauf" if lang == "de" else "Shopping")
        count_label = str(len(events)) + ("+" if overflow else "")
        title = f"{list_name}: {count_label} " + ("Änderung" if len(events) == 1 else "Änderungen") if lang == "de" else f"{list_name}: {count_label} change" + ("s" if len(events) != 1 else "")
        labels = {"created": ("hinzugefügt", "added"), "completed": ("abgehakt", "checked"), "reopened": ("wieder offen", "reopened"), "updated": ("geändert", "updated"), "cleared": ("aufgeräumt", "cleaned up")}
        counts = {}
        for event in events:
            action = event["event_type"].split(".")[-1]
            counts[action] = counts.get(action, 0) + 1
        body = ", ".join(f"{count} {labels.get(action, labels['updated'])[lang == 'en']}" for action, count in counts.items())
        if overflow:
            body += " und weitere Änderungen" if lang == "de" else " and more changes"
        if names:
            body += ": " + ", ".join(name[:60] for name in names[:3]) + (" …" if len(names) > 3 else "")
        ctx = dict(first["context"])
        ctx.pop("item_id", None)
        return title[:160], body[:300], _target_url("shopping.items.cleared", ctx)
    first = events[0]
    spec = EVENT_SPECS[first["event_type"]]
    ctx = _SafeContext(first["context"])
    title = spec["title"][lang].format_map(ctx)
    body = spec["body"][lang].format_map(ctx)
    if len(events) > 1:
        body += f" (+{len(events) - 1})"
    return title[:160], body[:300], first.get("url") or _target_url(first["event_type"], ctx)


def flush_notification_batches(now=None, limit=100):
    """Row locks prevent parallel schedulers sending the same batch. Retry with stable tags."""
    now = now or timezone.now()
    sent = errors = 0
    ids = list(NotificationBatch.objects.filter(delivered_at__isnull=True, due_at__lte=now).order_by("due_at").values_list("pk", flat=True)[:limit])
    for pk in ids:
        with transaction.atomic():
            batch = NotificationBatch.objects.select_for_update(of=("self",)).select_related("membership__family", "membership__user").filter(pk=pk, delivered_at__isnull=True, due_at__lte=now).first()
            if not batch:
                continue
            member = batch.membership
            pref = NotificationPreference.objects.filter(membership=member).first()
            if member.family.status != Family.Status.ACTIVE or not member.user.is_active:
                batch.delete()
                continue
            if is_quiet(pref, member.family, now):
                batch.due_at = now + timedelta(minutes=5)
                batch.save(update_fields=["due_at"])
                continue
            events = _visible_events(batch, pref)
            if not events:
                batch.delete()
                continue
            title, body, url = _render(batch, events)
            try:
                result = send_user_push(member.user, title, body, url, tag=f"fam-uh-le:{member.family_id}:{batch.bucket}")
            except Exception:
                result = {"sent": 0, "errors": 1}
            sent += result.get("sent", 0)
            errors += result.get("errors", 0)
            batch.attempts += 1
            if result.get("errors") and batch.attempts < 5:
                batch.due_at = now + timedelta(minutes=2 ** batch.attempts)
            else:
                batch.delivered_at = now
                batch.events = {}  # Don't retain shopping names after delivery.
            batch.save(update_fields=["attempts", "due_at", "delivered_at", "events", "updated_at"])
    NotificationBatch.objects.filter(updated_at__lt=now - timedelta(days=7)).delete()
    return {"sent": sent, "errors": errors}
