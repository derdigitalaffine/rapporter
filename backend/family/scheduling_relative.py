from copy import deepcopy
from datetime import datetime, time, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.db import transaction

from .action_schedule import WEEKDAYS, local_datetime
from .models import FamilyEvent, Membership, Task
from .scheduling_models import SchedulingDependency, SchedulingMaterialization
from .unified_action_models import Action
from .unified_action_service import mirror


VERSION = "relative-schedule-v1"
DIRECTIONS = {"before": -1, "after": 1}
UNITS = {"minutes": "minutes", "hours": "hours", "days": "days", "weeks": "weeks"}
WEEKDAY_MODES = {"before", "after", "on_or_before", "on_or_after"}
WEEKEND_POLICIES = {"keep", "previous_weekday", "next_weekday", "skip"}
INHERITABLE_FIELDS = {"title", "location", "description", "participants", "duration", "assignee", "priority"}


def _clock(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("time must use HH:MM.")
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("time must use HH:MM.") from exc
    if parsed.second or parsed.microsecond:
        raise ValueError("time must use HH:MM.")
    return parsed


def normalize_relative_rule(value):
    if not isinstance(value, dict):
        raise ValueError("Relative rule must be an object.")
    allowed = {"version", "direction", "offset", "weekday", "time", "weekend_policy"}
    if set(value) - allowed:
        raise ValueError("Unsupported relative rule fields.")
    if value.get("version", VERSION) != VERSION:
        raise ValueError("Unsupported relative rule version.")
    direction = value.get("direction", "before")
    if direction not in DIRECTIONS:
        raise ValueError("direction must be before or after.")
    offset = value.get("offset", {"value": 0, "unit": "days"})
    if not isinstance(offset, dict) or set(offset) - {"value", "unit"}:
        raise ValueError("Invalid offset.")
    amount = offset.get("value", 0)
    unit = offset.get("unit", "days")
    if type(amount) is not int or not 0 <= amount <= 10000 or unit not in UNITS:
        raise ValueError("Invalid relative offset.")
    weekday = value.get("weekday")
    if weekday is not None:
        if not isinstance(weekday, dict) or set(weekday) != {"day", "mode"}:
            raise ValueError("Invalid weekday relationship.")
        if weekday.get("day") not in WEEKDAYS or weekday.get("mode") not in WEEKDAY_MODES:
            raise ValueError("Invalid weekday relationship.")
    at_time = value.get("time")
    _clock(at_time)
    weekend_policy = value.get("weekend_policy", "keep")
    if weekend_policy not in WEEKEND_POLICIES:
        raise ValueError("Invalid weekend policy.")
    result = {
        "version": VERSION,
        "direction": direction,
        "offset": {"value": amount, "unit": unit},
        "weekend_policy": weekend_policy,
    }
    if weekday:
        result["weekday"] = deepcopy(weekday)
    if at_time:
        result["time"] = at_time
    return result


def normalize_dependency_blueprint(output_type, value):
    value = value or {}
    if not isinstance(value, dict):
        raise ValueError("Output blueprint must be an object.")
    allowed = {"title", "duration_minutes", "location", "description", "notes", "assignee_user_id", "priority", "is_family_event"}
    if set(value) - allowed:
        raise ValueError("Unsupported output blueprint fields.")
    title = value.get("title", "")
    if title and (not isinstance(title, str) or len(title.strip()) > 200):
        raise ValueError("Invalid output title.")
    duration = value.get("duration_minutes", 60)
    if output_type == SchedulingDependency.OutputType.EVENT and (type(duration) is not int or not 1 <= duration <= 10080):
        raise ValueError("duration_minutes must be between 1 and 10080.")
    if "priority" in value and value["priority"] not in {"low", "normal", "high"}:
        raise ValueError("Invalid priority.")
    if "is_family_event" in value and type(value["is_family_event"]) is not bool:
        raise ValueError("is_family_event must be boolean.")
    return deepcopy(value)


def normalize_inheritance(value):
    value = value or {}
    if not isinstance(value, dict) or set(value) - INHERITABLE_FIELDS:
        raise ValueError("Invalid inheritance mapping.")
    if any(type(flag) is not bool for flag in value.values()):
        raise ValueError("Inheritance flags must be boolean.")
    return {key: bool(value[key]) for key in sorted(value)}


def _weekday_shift(day, target, mode):
    target_index = WEEKDAYS.index(target)
    current = day.weekday()
    if mode == "before":
        distance = (current - target_index) % 7 or 7
        return day - timedelta(days=distance)
    if mode == "after":
        distance = (target_index - current) % 7 or 7
        return day + timedelta(days=distance)
    if mode == "on_or_before":
        return day - timedelta(days=(current - target_index) % 7)
    return day + timedelta(days=(target_index - current) % 7)


def apply_relative_rule(anchor_at, rule, timezone_name):
    """Calculate in family wall-clock time and resolve DST gaps deterministically."""
    normalized = normalize_relative_rule(rule)
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise ValueError("Invalid family timezone.") from exc
    if not isinstance(anchor_at, datetime):
        raise ValueError("anchor_at must be a datetime.")
    if anchor_at.tzinfo is None:
        anchor_at = anchor_at.replace(tzinfo=zone)
    local = anchor_at.astimezone(zone).replace(tzinfo=None)
    offset = normalized["offset"]
    delta = timedelta(**{UNITS[offset["unit"]]: offset["value"]})
    local = local + DIRECTIONS[normalized["direction"]] * delta
    target_day = local.date()
    if normalized.get("weekday"):
        target_day = _weekday_shift(target_day, normalized["weekday"]["day"], normalized["weekday"]["mode"])
    policy = normalized["weekend_policy"]
    if target_day.weekday() >= 5:
        if policy == "skip":
            return None
        if policy == "previous_weekday":
            while target_day.weekday() >= 5:
                target_day -= timedelta(days=1)
        elif policy == "next_weekday":
            while target_day.weekday() >= 5:
                target_day += timedelta(days=1)
    clock = _clock(normalized.get("time")) or local.time().replace(tzinfo=None)
    return local_datetime(target_day, clock, zone)


def describe_relative_rule(rule, language="de"):
    rule = normalize_relative_rule(rule)
    de = str(language).lower().startswith("de")
    amount = rule["offset"]["value"]
    unit = rule["offset"]["unit"]
    units = {
        "minutes": ("Minute", "Minuten", "minute", "minutes"),
        "hours": ("Stunde", "Stunden", "hour", "hours"),
        "days": ("Tag", "Tage", "day", "days"),
        "weeks": ("Woche", "Wochen", "week", "weeks"),
    }
    if amount:
        names = units[unit]
        label = names[0 if amount == 1 else 1] if de else names[2 if amount == 1 else 3]
        text = f"{amount} {label} {'vorher' if rule['direction']=='before' else 'nachher'}" if de else f"{amount} {label} {'before' if rule['direction']=='before' else 'after'}"
    else:
        text = "Am selben Zeitpunkt" if de else "At the same time"
    if rule.get("weekday"):
        day_names = {
            "MO": ("Montag", "Monday"), "TU": ("Dienstag", "Tuesday"), "WE": ("Mittwoch", "Wednesday"),
            "TH": ("Donnerstag", "Thursday"), "FR": ("Freitag", "Friday"), "SA": ("Samstag", "Saturday"), "SU": ("Sonntag", "Sunday"),
        }
        mode = rule["weekday"]["mode"]
        day = day_names[rule["weekday"]["day"]][0 if de else 1]
        mode_label = {
            "before": ("davor", "before"), "after": ("danach", "after"),
            "on_or_before": ("am oder davor", "on or before"), "on_or_after": ("am oder danach", "on or after"),
        }[mode][0 if de else 1]
        text += f" · {day} {mode_label}"
    if rule.get("time"):
        text += f" · {rule['time']}"
    return text


def _anchor_title(anchor):
    return getattr(anchor, "title", None) or getattr(anchor, "name", None) or ""


def _projected_payload(dependency, anchor, scheduled_for):
    blueprint = normalize_dependency_blueprint(dependency.output_type, dependency.output_blueprint)
    inheritance = normalize_inheritance(dependency.inheritance)
    title = blueprint.get("title") or (_anchor_title(anchor) if inheritance.get("title") else "")
    if not title:
        title = "Folgetermin" if dependency.output_type == SchedulingDependency.OutputType.EVENT else "Folgeaufgabe"
    payload = {**blueprint, "title": title, "scheduled_for": scheduled_for.isoformat()}
    if isinstance(anchor, FamilyEvent):
        source = anchor.payload if isinstance(anchor.payload, dict) else {}
        if inheritance.get("location") and not payload.get("location"):
            payload["location"] = source.get("location", "")
        if inheritance.get("description") and not payload.get("description"):
            payload["description"] = source.get("description", "")
        if inheritance.get("duration") and anchor.starts_at and anchor.ends_at:
            payload["duration_minutes"] = max(1, int((anchor.ends_at - anchor.starts_at).total_seconds() // 60))
        if inheritance.get("participants"):
            payload["participant_ids"] = [str(value) for value in anchor.participants.values_list("id", flat=True)]
        if inheritance.get("is_family_event"):
            payload["is_family_event"] = bool(anchor.is_family_event)
    elif isinstance(anchor, Action):
        if inheritance.get("assignee") and anchor.assignee_id and not payload.get("assignee_user_id"):
            payload["assignee_user_id"] = anchor.assignee_id
        if inheritance.get("priority") and not payload.get("priority"):
            payload["priority"] = anchor.priority
    return payload


def _dedupe_key(dependency, occurrence_key):
    raw = f"{dependency.id}:{occurrence_key}:{dependency.output_type}".encode("utf-8")
    return sha256(raw).hexdigest()


@transaction.atomic
def materialize_dependency(dependency, anchor, anchor_at, occurrence_key):
    """Create or recalculate one derived Event/Todo idempotently."""
    if not dependency.enabled:
        return None
    scheduled_for = apply_relative_rule(anchor_at, dependency.relative_rule, dependency.family.timezone)
    if scheduled_for is None:
        return None
    occurrence_key = str(occurrence_key or anchor_at.isoformat())[:96]
    key = _dedupe_key(dependency, occurrence_key)
    projected = _projected_payload(dependency, anchor, scheduled_for)
    materialization, created = SchedulingMaterialization.objects.select_for_update().get_or_create(
        family=dependency.family,
        dedupe_key=key,
        defaults={
            "dependency": dependency,
            "anchor_occurrence_key": occurrence_key,
            "output_type": dependency.output_type,
            "scheduled_for": scheduled_for,
            "projected_payload": projected,
            "provenance": {"relative_rule": dependency.relative_rule, "inheritance": dependency.inheritance, "detached_fields": []},
        },
    )
    if materialization.status == SchedulingMaterialization.Status.DETACHED:
        return materialization
    detached = set((materialization.provenance or {}).get("detached_fields", []))
    effective = dict(projected)
    for field in detached:
        if field in materialization.projected_payload:
            effective[field] = materialization.projected_payload[field]
    if "scheduled_for" in detached:
        scheduled_for = materialization.scheduled_for
        effective["scheduled_for"] = scheduled_for.isoformat()

    output_id = materialization.output_id
    if dependency.output_type == SchedulingDependency.OutputType.EVENT:
        event = FamilyEvent.objects.filter(family=dependency.family, id=output_id).first() if output_id else None
        duration = int(effective.get("duration_minutes") or 60)
        values = {
            "type": "calendar.event",
            "title": effective["title"],
            "starts_at": scheduled_for,
            "ends_at": scheduled_for + timedelta(minutes=duration),
            "actionable": False,
            "is_family_event": bool(effective.get("is_family_event", False)),
            "payload": {
                "provider": "FamilyOS",
                "location": effective.get("location", ""),
                "description": effective.get("description", ""),
                "scheduling_origin": {"dependency_id": str(dependency.id), "occurrence_key": occurrence_key},
            },
        }
        if event is None:
            event = FamilyEvent.objects.create(family=dependency.family, **values)
        else:
            for field, value in values.items():
                if field not in detached:
                    setattr(event, field, value)
            event.save()
        if "participants" not in detached and "participant_ids" in effective:
            event.participants.set(Membership.objects.filter(family=dependency.family, id__in=effective["participant_ids"]))
        output_id = event.id
    elif dependency.output_type == SchedulingDependency.OutputType.ACTION:
        row = Action.objects.filter(family=dependency.family, id=output_id).select_related("legacy_task").first() if output_id else None
        task = row.legacy_task if row and row.legacy_task_id else None
        values = {
            "title": effective["title"],
            "notes": effective.get("notes", ""),
            "due_at": scheduled_for,
            "priority": effective.get("priority", "normal"),
            "source": f"scheduling:{dependency.id}",
        }
        if effective.get("assignee_user_id"):
            membership = Membership.objects.filter(family=dependency.family, user_id=effective["assignee_user_id"]).first()
            if membership:
                values["assignee_id"] = membership.user_id
        if task is None:
            task = Task.objects.create(family=dependency.family, created_by=dependency.created_by, **values)
            row = mirror(task)
        else:
            for field, value in values.items():
                logical = "scheduled_for" if field == "due_at" else field
                if logical not in detached:
                    setattr(task, field, value)
            task.save()
            row = mirror(task)
        output_id = row.id
    else:
        materialization.status = SchedulingMaterialization.Status.PROJECTED
        materialization.scheduled_for = scheduled_for
        materialization.projected_payload = effective
        materialization.save(update_fields=["status", "scheduled_for", "projected_payload", "updated_at"])
        return materialization

    materialization.output_id = output_id
    materialization.scheduled_for = scheduled_for
    materialization.projected_payload = effective
    materialization.status = SchedulingMaterialization.Status.MATERIALIZED
    materialization.save(update_fields=["output_id", "scheduled_for", "projected_payload", "status", "updated_at"])
    return materialization


@transaction.atomic
def detach_materialization_fields(materialization, fields):
    if not isinstance(fields, list) or any(field not in {"scheduled_for", "title", "location", "description", "participants", "duration", "notes", "assignee", "priority"} for field in fields):
        raise ValidationError({"fields": "Unsupported detached fields."})
    provenance = dict(materialization.provenance or {})
    provenance["detached_fields"] = sorted(set(fields))
    materialization.provenance = provenance
    materialization.save(update_fields=["provenance", "updated_at"])
    return materialization
