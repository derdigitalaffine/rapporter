from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .models import AutomationExecution, AutomationRule, FamilyEvent, InboxItem, IntegrationSource, ShoppingItem, ShoppingList, Task, TaskList


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
        return [{"event": e, "event_title": e.title, "temp_min": e.payload.get("temp_min")} for e in events if e.payload.get("temp_min") is not None and float(e.payload["temp_min"]) <= threshold]

    if trigger == AutomationRule.Trigger.WEATHER_RAIN:
        hours = int(cfg.get("within_hours", 36))
        threshold = float(cfg.get("probability", 70))
        events = FamilyEvent.objects.filter(family=rule.family, type="weather.forecast", starts_at__gte=now, starts_at__lte=now + timedelta(hours=hours))
        return [{"event": e, "event_title": e.title, "rain_probability": e.payload.get("rain_probability")} for e in events if e.payload.get("rain_probability") is not None and float(e.payload["rain_probability"]) >= threshold]

    if trigger == AutomationRule.Trigger.WARNING_ACTIVE:
        base = FamilyEvent.objects.filter(family=rule.family, type__in=["weather.warning", "public.warning"], starts_at__lte=now)
        events = base.filter(ends_at__isnull=True) | base.filter(ends_at__gte=now)
        return [{"event": e, "event_title": e.title, "severity": e.payload.get("severity") or e.payload.get("level")} for e in events.distinct()]

    if trigger == AutomationRule.Trigger.EVENT_UPCOMING:
        hours = int(cfg.get("within_hours", 24))
        event_type = cfg.get("event_type", "calendar.event")
        contains = str(cfg.get("title_contains", "")).casefold().strip()
        events = FamilyEvent.objects.filter(family=rule.family, type=event_type, starts_at__gte=now, starts_at__lte=now + timedelta(hours=hours))
        return [{"event": e, "event_title": e.title} for e in events if not contains or contains in e.title.casefold()]

    if trigger == AutomationRule.Trigger.DAILY:
        target = str(cfg.get("time", "08:00"))
        try:
            hour, minute = [int(x) for x in target.split(":", 1)]
        except Exception:
            hour, minute = 8, 0
        if local_now.hour == hour and abs(local_now.minute - minute) <= 10:
            return [{"date": local_now.date().isoformat()}]
        return []

    if trigger == AutomationRule.Trigger.HOME_STATE:
        entity_id = str(cfg.get("entity_id") or "").strip()
        desired_state = str(cfg.get("state") or "").casefold().strip()
        source_id = cfg.get("integration_source")
        events = FamilyEvent.objects.filter(family=rule.family, type="home.state")
        if source_id:
            events = events.filter(source_id=source_id)
        contexts = []
        for event in events:
            payload = event.payload or {}
            if entity_id and payload.get("entity_id") != entity_id:
                continue
            state = str(payload.get("state") or "")
            if desired_state and state.casefold() != desired_state:
                continue
            last_changed = payload.get("last_changed") or event.updated_at.isoformat()
            contexts.append({"event": event, "event_title": event.title, "entity_id": payload.get("entity_id", ""), "entity_name": event.title, "state": state, "fingerprint": f"home:{event.id}:{state}:{last_changed}"})
        return contexts

    if trigger == AutomationRule.Trigger.TRANSIT_DELAY:
        threshold = int(cfg.get("minutes", 5))
        hours = int(cfg.get("within_hours", 2))
        source_id = cfg.get("integration_source")
        events = FamilyEvent.objects.filter(family=rule.family, type="transit.departure", starts_at__gte=now, starts_at__lte=now + timedelta(hours=hours))
        if source_id:
            events = events.filter(source_id=source_id)
        contexts = []
        for event in events:
            payload = event.payload or {}
            delay = int(payload.get("delay_minutes") or 0)
            if delay < threshold:
                continue
            contexts.append({"event": event, "event_title": event.title, "line": payload.get("line", ""), "destination": payload.get("destination", ""), "stop": payload.get("stop", ""), "delay_minutes": delay})
        return contexts

    if trigger == AutomationRule.Trigger.TASK_COMPLETED:
        contains = str(cfg.get("title_contains") or "").casefold().strip()
        task_list = cfg.get("task_list")
        tasks = Task.objects.filter(family=rule.family, completed_at__isnull=False, completed_at__gte=now - timedelta(days=90)).select_related("task_list")
        if task_list:
            tasks = tasks.filter(task_list_id=task_list)
        contexts = []
        for task in tasks:
            if contains and contains not in task.title.casefold():
                continue
            contexts.append({"task": task, "task_title": task.title, "event_title": task.title, "list_name": task.task_list.name if task.task_list else "", "completed_at": task.completed_at.isoformat(), "fingerprint": f"task:{task.id}:completed:{task.completed_at.isoformat()}"})
        return contexts

    return []


def _fingerprint(rule, context):
    if context.get("fingerprint"):
        return f"{rule.id}:{context['fingerprint']}"
    task = context.get("task")
    if task:
        return f"{rule.id}:task:{task.id}:{task.completed_at}"
    event = context.get("event")
    if event:
        return f"{rule.id}:event:{event.id}"
    return f"{rule.id}:date:{context.get('date') or _local_now(rule.family).date().isoformat()}"


def _render(value, context):
    text = str(value or "")
    for key, val in context.items():
        if key in {"event", "task"}:
            continue
        text = text.replace("{" + key + "}", str(val if val is not None else ""))
    return text


def _act(rule, context):
    cfg = rule.action_config or {}
    if rule.action_type == AutomationRule.Action.TASK_CREATE:
        task_list = TaskList.objects.filter(id=cfg.get("task_list"), family=rule.family).first() if cfg.get("task_list") else None
        task_list = task_list or TaskList.objects.filter(family=rule.family, archived=False).first() or TaskList.objects.create(family=rule.family, name="Allgemein", icon="list-check")
        return Task.objects.create(family=rule.family, task_list=task_list, title=_render(cfg.get("title") or "{event_title}", context), notes=_render(cfg.get("notes", ""), context), priority=cfg.get("priority", Task.Priority.NORMAL), source=f"rule:{rule.id}")
    if rule.action_type == AutomationRule.Action.SHOPPING_ADD:
        shopping = ShoppingList.objects.filter(id=cfg.get("shopping_list"), family=rule.family, archived=False).first() if cfg.get("shopping_list") else None
        shopping = shopping or ShoppingList.objects.filter(family=rule.family, archived=False).order_by("sort_order", "created_at").first() or ShoppingList.objects.create(family=rule.family, name="Einkauf")
        name = _render(cfg.get("name") or "{event_title}", context)
        item = ShoppingItem.objects.filter(shopping_list=shopping, name__iexact=name).order_by("checked", "-updated_at").first() or ShoppingItem(shopping_list=shopping, name=name)
        item.checked = False; item.checked_at = None
        if cfg.get("quantity"): item.quantity = _render(cfg["quantity"], context)
        if cfg.get("category"): item.category = _render(cfg["category"], context)
        item.save(); return item
    if rule.action_type == AutomationRule.Action.INBOX_CREATE:
        return InboxItem.objects.create(family=rule.family, source="automation", title=_render(cfg.get("title") or "{event_title}", context), body=_render(cfg.get("body", ""), context), parsed={"rule_id": str(rule.id)})
    if rule.action_type == AutomationRule.Action.HOME_SERVICE:
        from .extended_integrations import home_assistant_service
        source = IntegrationSource.objects.filter(id=cfg.get("integration_source"), family=rule.family, kind=IntegrationSource.Kind.HOME, config__adapter="home_assistant").first()
        if not source:
            raise ValueError("Home-Assistant-Integration für die Regel fehlt.")
        data = cfg.get("data") if isinstance(cfg.get("data"), dict) else {}
        return home_assistant_service(source, _render(cfg.get("domain") or "homeassistant", context), _render(cfg.get("service") or "turn_on", context), entity_id=_render(cfg.get("entity_id", ""), context), data=data)
    if rule.action_type == AutomationRule.Action.PUSH_NOTIFY:
        from .push import send_family_push
        return send_family_push(rule.family, _render(cfg.get("title") or "{event_title}", context), _render(cfg.get("body", ""), context), _render(cfg.get("url") or "/", context), tag=f"rule-{rule.id}")
    raise ValueError("Unsupported automation action")


def _result_message(obj):
    if hasattr(obj, "pk"):
        return f"{obj.__class__.__name__}:{obj.pk}"
    if isinstance(obj, dict):
        if "sent" in obj:
            return f"Push:{obj.get('sent',0)}"
        return "Action:ok"
    return str(obj)[:500]


def run_rule(rule):
    if not rule.enabled:
        return 0
    count = 0
    for context in _contexts(rule):
        fingerprint = _fingerprint(rule, context)
        with transaction.atomic():
            execution, created = AutomationExecution.objects.get_or_create(rule=rule, fingerprint=fingerprint, defaults={"status": "running"})
            if not created:
                if execution.status != "error" or execution.updated_at > timezone.now() - timedelta(minutes=5):
                    continue
                execution.status = "running"; execution.message = ""; execution.save(update_fields=["status", "message", "updated_at"])
            try:
                obj = _act(rule, context)
                execution.status = "success"; execution.message = _result_message(obj); execution.save(update_fields=["status", "message", "updated_at"]); count += 1
            except Exception as exc:
                execution.status = "error"; execution.message = str(exc)[:500]; execution.save(update_fields=["status", "message", "updated_at"])
    rule.last_run_at = timezone.now(); rule.save(update_fields=["last_run_at", "updated_at"])
    return count


def run_all_rules():
    return sum(run_rule(rule) for rule in AutomationRule.objects.filter(enabled=True).select_related("family"))


RULE_TEMPLATES = [
    {"id": "waste-out", "name": "Müll rausstellen", "description": "Wenn morgen Müllabfuhr ist, Aufgabe zum Rausstellen anlegen.", "trigger_type": "waste_tomorrow", "trigger_config": {}, "action_type": "task_create", "action_config": {"title": "{event_title} rausstellen", "priority": "normal"}, "icon": "trash-can"},
    {"id": "frost-plants", "name": "Pflanzen bei Frost reinholen", "description": "Wenn Frost angekündigt ist, Aufgabe für die Pflanzen anlegen.", "trigger_type": "weather_frost", "trigger_config": {"temperature": 0, "within_hours": 36}, "action_type": "task_create", "action_config": {"title": "Frost angekündigt – Pflanzen reinholen", "priority": "high"}, "icon": "snowflake"},
    {"id": "warning-inbox", "name": "Amtliche Warnungen in die Inbox", "description": "Wenn eine DWD/NINA-Warnung aktiv ist, in der Familien-Inbox anzeigen.", "trigger_type": "warning_active", "trigger_config": {}, "action_type": "inbox_create", "action_config": {"title": "{event_title}", "body": "Amtliche Warnung – bitte prüfen."}, "icon": "triangle-exclamation"},
    {"id": "warning-push", "name": "Amtliche Warnung aufs Handy", "description": "Wenn eine DWD/NINA-Warnung aktiv wird, Push-Benachrichtigung an registrierte Familiengeräte senden.", "trigger_type": "warning_active", "trigger_config": {}, "action_type": "push_notify", "action_config": {"title": "{event_title}", "body": "Amtliche Warnung – Details in fam-uh-le öffnen.", "url": "/?page=calendar"}, "icon": "bell"},
    {"id": "rain-laundry", "name": "Wäsche bei Regen erinnern", "description": "Wenn hohe Regenwahrscheinlichkeit besteht, Aufgabe anlegen.", "trigger_type": "weather_rain", "trigger_config": {"probability": 75, "within_hours": 24}, "action_type": "task_create", "action_config": {"title": "Regen wahrscheinlich – Wäsche reinholen", "priority": "normal"}, "icon": "cloud-rain"},
    {"id": "transit-delay", "name": "ÖPNV-Verspätung melden", "description": "Wenn eine VRN-Abfahrt mindestens 10 Minuten verspätet ist, Hinweis in die Familien-Inbox legen.", "trigger_type": "transit_delay", "trigger_config": {"minutes": 10, "within_hours": 2}, "action_type": "inbox_create", "action_config": {"title": "{line} verspätet", "body": "{line} Richtung {destination}: {delay_minutes} Minuten Verspätung ab {stop}."}, "icon": "bus"},
]
