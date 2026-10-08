from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .models import AutomationExecution, AutomationRule, FamilyEvent, InboxItem, ShoppingItem, ShoppingList, Task, TaskList


def _local_now(family):
    try:
        return timezone.now().astimezone(ZoneInfo(family.timezone))
    except Exception:
        return timezone.localtime()


def _contexts(rule):
    now = timezone.now()
    local_now = _local_now(rule.family)
    cfg = rule.trigger_config or {}
    trigger = rule.trigger_type

    if trigger == AutomationRule.Trigger.WASTE_TOMORROW:
        tomorrow = local_now.date() + timedelta(days=1)
        events = FamilyEvent.objects.filter(family=rule.family, type="waste.collection", starts_at__date=tomorrow)
        return [{"event": e, "event_title": e.title, "date": tomorrow.isoformat()} for e in events]

    if trigger == AutomationRule.Trigger.WEATHER_FROST:
        hours = int(cfg.get("within_hours", 36))
        threshold = float(cfg.get("temperature", 0))
        events = FamilyEvent.objects.filter(family=rule.family, type="weather.forecast", starts_at__gte=now, starts_at__lte=now + timedelta(hours=hours))
        return [
            {"event": e, "event_title": e.title, "temp_min": e.payload.get("temp_min")}
            for e in events
            if e.payload.get("temp_min") is not None and float(e.payload["temp_min"]) <= threshold
        ]

    if trigger == AutomationRule.Trigger.WEATHER_RAIN:
        hours = int(cfg.get("within_hours", 36))
        threshold = float(cfg.get("probability", 70))
        events = FamilyEvent.objects.filter(family=rule.family, type="weather.forecast", starts_at__gte=now, starts_at__lte=now + timedelta(hours=hours))
        return [
            {"event": e, "event_title": e.title, "rain_probability": e.payload.get("rain_probability")}
            for e in events
            if e.payload.get("rain_probability") is not None and float(e.payload["rain_probability"]) >= threshold
        ]

    if trigger == AutomationRule.Trigger.WARNING_ACTIVE:
        events = FamilyEvent.objects.filter(family=rule.family, type__in=["weather.warning", "public.warning"], starts_at__lte=now).filter(ends_at__isnull=True) | FamilyEvent.objects.filter(family=rule.family, type__in=["weather.warning", "public.warning"], starts_at__lte=now, ends_at__gte=now)
        return [{"event": e, "event_title": e.title, "severity": e.payload.get("severity") or e.payload.get("level")} for e in events.distinct()]

    if trigger == AutomationRule.Trigger.EVENT_UPCOMING:
        hours = int(cfg.get("within_hours", 24))
        event_type = cfg.get("event_type", "calendar.event")
        contains = str(cfg.get("title_contains", "")).lower().strip()
        events = FamilyEvent.objects.filter(family=rule.family, type=event_type, starts_at__gte=now, starts_at__lte=now + timedelta(hours=hours))
        return [{"event": e, "event_title": e.title} for e in events if not contains or contains in e.title.lower()]

    if trigger == AutomationRule.Trigger.DAILY:
        target = str(cfg.get("time", "08:00"))
        try:
            hour, minute = [int(x) for x in target.split(":", 1)]
        except Exception:
            hour, minute = 8, 0
        if local_now.hour == hour and abs(local_now.minute - minute) <= 10:
            return [{"date": local_now.date().isoformat()}]
        return []

    return []


def _fingerprint(rule, context):
    event = context.get("event")
    if event:
        return f"{rule.id}:event:{event.id}"
    return f"{rule.id}:date:{context.get('date') or _local_now(rule.family).date().isoformat()}"


def _render(value, context):
    text = str(value or "")
    for key, val in context.items():
        if key == "event":
            continue
        text = text.replace("{" + key + "}", str(val if val is not None else ""))
    return text


def _act(rule, context):
    cfg = rule.action_config or {}
    if rule.action_type == AutomationRule.Action.TASK_CREATE:
        task_list = None
        if cfg.get("task_list"):
            task_list = TaskList.objects.filter(id=cfg["task_list"], family=rule.family).first()
        return Task.objects.create(
            family=rule.family,
            task_list=task_list,
            title=_render(cfg.get("title") or "{event_title}", context),
            notes=_render(cfg.get("notes", ""), context),
            priority=cfg.get("priority", Task.Priority.NORMAL),
            source=f"rule:{rule.id}",
        )
    if rule.action_type == AutomationRule.Action.SHOPPING_ADD:
        shopping = None
        if cfg.get("shopping_list"):
            shopping = ShoppingList.objects.filter(id=cfg["shopping_list"], family=rule.family, archived=False).first()
        shopping = shopping or ShoppingList.objects.filter(family=rule.family, archived=False).first()
        if not shopping:
            shopping = ShoppingList.objects.create(family=rule.family, name="Einkauf")
        name = _render(cfg.get("name") or "{event_title}", context)
        item, _ = ShoppingItem.objects.get_or_create(shopping_list=shopping, name=name, checked=False, defaults={"quantity": cfg.get("quantity", ""), "category": cfg.get("category", "")})
        return item
    if rule.action_type == AutomationRule.Action.INBOX_CREATE:
        return InboxItem.objects.create(
            family=rule.family,
            source="automation",
            title=_render(cfg.get("title") or "{event_title}", context),
            body=_render(cfg.get("body", ""), context),
            parsed={"rule_id": str(rule.id)},
        )
    raise ValueError("Unsupported automation action")


def run_rule(rule):
    if not rule.enabled:
        return 0
    count = 0
    for context in _contexts(rule):
        fingerprint = _fingerprint(rule, context)
        with transaction.atomic():
            execution, created = AutomationExecution.objects.get_or_create(rule=rule, fingerprint=fingerprint, defaults={"status": "running"})
            if not created:
                continue
            try:
                obj = _act(rule, context)
                execution.status = "success"
                execution.message = f"{obj.__class__.__name__}:{obj.pk}"
                execution.save(update_fields=["status", "message", "updated_at"])
                count += 1
            except Exception as exc:
                execution.status = "error"
                execution.message = str(exc)[:500]
                execution.save(update_fields=["status", "message", "updated_at"])
    rule.last_run_at = timezone.now()
    rule.save(update_fields=["last_run_at", "updated_at"])
    return count


def run_all_rules():
    total = 0
    for rule in AutomationRule.objects.filter(enabled=True).select_related("family"):
        total += run_rule(rule)
    return total


RULE_TEMPLATES = [
    {"id": "waste-out", "name": "Müll rausstellen", "description": "Wenn morgen Müllabfuhr ist, Aufgabe zum Rausstellen anlegen.", "trigger_type": "waste_tomorrow", "trigger_config": {}, "action_type": "task_create", "action_config": {"title": "{event_title} rausstellen", "priority": "normal"}, "icon": "trash-can"},
    {"id": "frost-plants", "name": "Pflanzen bei Frost reinholen", "description": "Wenn Frost angekündigt ist, Aufgabe für die Pflanzen anlegen.", "trigger_type": "weather_frost", "trigger_config": {"temperature": 0, "within_hours": 36}, "action_type": "task_create", "action_config": {"title": "Frost angekündigt – Pflanzen reinholen", "priority": "high"}, "icon": "snowflake"},
    {"id": "warning-inbox", "name": "Amtliche Warnungen in die Inbox", "description": "Wenn eine DWD/NINA-Warnung aktiv ist, in der Familien-Inbox anzeigen.", "trigger_type": "warning_active", "trigger_config": {}, "action_type": "inbox_create", "action_config": {"title": "{event_title}", "body": "Amtliche Warnung – bitte prüfen."}, "icon": "triangle-exclamation"},
    {"id": "rain-laundry", "name": "Wäsche bei Regen erinnern", "description": "Wenn hohe Regenwahrscheinlichkeit besteht, Aufgabe anlegen.", "trigger_type": "weather_rain", "trigger_config": {"probability": 75, "within_hours": 24}, "action_type": "task_create", "action_config": {"title": "Regen wahrscheinlich – Wäsche reinholen", "priority": "normal"}, "icon": "cloud-rain"},
]
