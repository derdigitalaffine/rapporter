"""Canonical, server-authoritative recurrence rules shared by calendar and actions.

The v1 contract deliberately wraps the recurrence vocabulary already used by
``action-schedule-v1`` instead of creating a second recurrence implementation.
Domain adapters keep existing event/action payloads compatible while new
features can target one normalized rule shape.
"""
from copy import deepcopy
from datetime import date
from zoneinfo import ZoneInfo

from .action_schedule import WEEKDAYS, _days, normalize_schedule, parse_schedule


VERSION = "scheduling-rule-v1"
TIME_MODES = {"wall_clock", "absolute"}
MAX_PREVIEW = 50
MAX_BOUND_COUNT = 10000
_COMMON_SCHEDULE_FIELDS = {"recurrence", "anchor_date", "segments", "excluded_weekdays", "exceptions"}
_ALLOWED_FIELDS = {
    "version",
    "timezone",
    "time_mode",
    *_COMMON_SCHEDULE_FIELDS,
    "bounds",
    "pauses",
    "include_dates",
    "exclude_dates",
}


def _iso_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date.") from exc


def _date_list(values, label, maximum=256):
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > maximum:
        raise ValueError(f"{label} must be a list with at most {maximum} dates.")
    normalized = []
    seen = set()
    for raw in values:
        day = _iso_date(raw, label)
        if day in seen:
            raise ValueError(f"{label} contains duplicate dates.")
        seen.add(day)
        normalized.append(day.isoformat())
    return sorted(normalized)


def normalize_scheduling_rule(value, family_timezone, anchor_date=None):
    """Validate and normalize ``scheduling-rule-v1``.

    Recurrence, weekday segments and occurrence exceptions are delegated to
    ``normalize_schedule`` so calendar and todo rules cannot drift apart.
    """
    if not isinstance(value, dict):
        raise ValueError("Scheduling rule must be an object.")
    value = deepcopy(value)
    if set(value) - _ALLOWED_FIELDS:
        raise ValueError("Unsupported scheduling rule fields.")
    if value.get("version", VERSION) != VERSION:
        raise ValueError("Unsupported scheduling rule version.")

    timezone_name = value.get("timezone") or family_timezone or "UTC"
    try:
        ZoneInfo(timezone_name)
    except (TypeError, ValueError):
        raise ValueError("Invalid timezone.")

    time_mode = value.get("time_mode", "wall_clock")
    if time_mode not in TIME_MODES:
        raise ValueError("Invalid time mode.")

    raw_anchor = value.get("anchor_date") or anchor_date
    if raw_anchor is None:
        raw_anchor = date.today().isoformat()
    anchor = _iso_date(raw_anchor, "anchor_date")

    schedule_input = {
        "version": "action-schedule-v1",
        "timezone": timezone_name,
        "mode": "static",
        "anchor_date": anchor.isoformat(),
    }
    for field in ("recurrence", "segments", "excluded_weekdays", "exceptions"):
        if field in value:
            schedule_input[field] = deepcopy(value[field])
    schedule = normalize_schedule(schedule_input, timezone_name, today=anchor)

    bounds = value.get("bounds", {})
    if not isinstance(bounds, dict) or set(bounds) - {"start_on", "end_on", "count"}:
        raise ValueError("Invalid scheduling bounds.")
    normalized_bounds = {}
    if bounds.get("start_on"):
        normalized_bounds["start_on"] = _iso_date(bounds["start_on"], "bounds.start_on").isoformat()
    if bounds.get("end_on"):
        normalized_bounds["end_on"] = _iso_date(bounds["end_on"], "bounds.end_on").isoformat()
    if "count" in bounds:
        count = bounds["count"]
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_BOUND_COUNT:
            raise ValueError(f"bounds.count must be between 1 and {MAX_BOUND_COUNT}.")
        normalized_bounds["count"] = count
    if normalized_bounds.get("start_on") and normalized_bounds.get("end_on"):
        if date.fromisoformat(normalized_bounds["start_on"]) > date.fromisoformat(normalized_bounds["end_on"]):
            raise ValueError("Scheduling bounds end before they start.")

    pauses = value.get("pauses", [])
    if not isinstance(pauses, list) or len(pauses) > 64:
        raise ValueError("At most 64 pause windows are supported.")
    normalized_pauses = []
    for pause in pauses:
        if not isinstance(pause, dict) or set(pause) != {"start_on", "end_on"}:
            raise ValueError("Pause windows require start_on and end_on.")
        start = _iso_date(pause["start_on"], "pauses.start_on")
        end = _iso_date(pause["end_on"], "pauses.end_on")
        if end < start:
            raise ValueError("Pause window ends before it starts.")
        normalized_pauses.append({"start_on": start.isoformat(), "end_on": end.isoformat()})
    normalized_pauses.sort(key=lambda item: (item["start_on"], item["end_on"]))

    include_dates = _date_list(value.get("include_dates"), "include_dates")
    exclude_dates = _date_list(value.get("exclude_dates"), "exclude_dates")
    if set(include_dates).intersection(exclude_dates):
        raise ValueError("A date cannot be both explicitly included and excluded.")

    result = {
        "version": VERSION,
        "timezone": timezone_name,
        "time_mode": time_mode,
        "anchor_date": schedule["anchor_date"],
        "recurrence": deepcopy(schedule.get("recurrence")),
    }
    for field in ("segments", "excluded_weekdays", "exceptions"):
        if schedule.get(field):
            result[field] = deepcopy(schedule[field])
    if normalized_bounds:
        result["bounds"] = normalized_bounds
    if normalized_pauses:
        result["pauses"] = normalized_pauses
    if include_dates:
        result["include_dates"] = include_dates
    if exclude_dates:
        result["exclude_dates"] = exclude_dates
    return result


def from_action_schedule(schedule, family_timezone):
    """Adapt a static ``action-schedule-v1`` value to the canonical rule."""
    normalized = normalize_schedule(schedule, family_timezone)
    if normalized.get("mode") != "static":
        raise ValueError("Learning/adaptive action schedules are behavior, not recurrence rules.")
    value = {
        "version": VERSION,
        "timezone": normalized["timezone"],
        "time_mode": "wall_clock",
    }
    for field in _COMMON_SCHEDULE_FIELDS:
        if field in normalized:
            value[field] = deepcopy(normalized[field])
    return normalize_scheduling_rule(value, family_timezone)


def to_action_schedule(rule, family_timezone):
    """Return the lossless ``action-schedule-v1`` representation.

    Bounds, pauses and explicit include/exclude dates require the universal
    runtime and are intentionally rejected instead of being silently dropped.
    """
    normalized = normalize_scheduling_rule(rule, family_timezone)
    if normalized["time_mode"] != "wall_clock":
        raise ValueError("Absolute-time rules are not representable in action-schedule-v1.")
    unsupported = [field for field in ("bounds", "pauses", "include_dates", "exclude_dates") if normalized.get(field)]
    if unsupported:
        raise ValueError("Universal rule features require the scheduling runtime: " + ", ".join(unsupported))
    result = {
        "version": "action-schedule-v1",
        "timezone": normalized["timezone"],
        "mode": "static",
        "anchor_date": normalized["anchor_date"],
        "recurrence": deepcopy(normalized["recurrence"]),
    }
    for field in ("segments", "excluded_weekdays", "exceptions"):
        if normalized.get(field):
            result[field] = deepcopy(normalized[field])
    return normalize_schedule(result, family_timezone)


def from_event_recurrence(value, starts_at, family_timezone):
    """Adapt the existing native-event recurrence payload without changing it."""
    if starts_at is None:
        raise ValueError("A recurring calendar event requires a start time.")
    from .calendar_recurrence import normalize_event_recurrence, recurrence_dict

    event_value = normalize_event_recurrence(value, starts_at, family_timezone)
    recurrence = recurrence_dict(event_value)
    if recurrence is None:
        raise ValueError("Calendar event has no recurrence.")
    local_start = starts_at.astimezone(ZoneInfo(family_timezone or "UTC"))
    return normalize_scheduling_rule(
        {
            "version": VERSION,
            "timezone": family_timezone or "UTC",
            "time_mode": "wall_clock",
            "anchor_date": local_start.date().isoformat(),
            "recurrence": recurrence,
        },
        family_timezone or "UTC",
    )


def to_event_recurrence(rule, family_timezone):
    """Return the structured recurrence accepted by the current event API."""
    normalized = normalize_scheduling_rule(rule, family_timezone)
    if normalized["time_mode"] != "wall_clock":
        raise ValueError("Absolute-time rules are not representable by the current event payload.")
    unsupported = [
        field
        for field in ("bounds", "pauses", "include_dates", "exclude_dates", "segments", "excluded_weekdays", "exceptions")
        if normalized.get(field)
    ]
    if unsupported:
        raise ValueError("Universal rule features require the scheduling runtime: " + ", ".join(unsupported))
    recurrence = normalized.get("recurrence")
    if not recurrence or recurrence.get("frequency") == "once":
        raise ValueError("Current event recurrence requires a repeating frequency.")
    return deepcopy(recurrence)


def parse_scheduling_text(text, family_timezone, today=None):
    """Parse deterministic DE/EN recurrence phrases; never calls an LLM."""
    schedule = parse_schedule(text, family_timezone, today=today)
    if schedule.get("mode") != "static":
        raise ValueError("Learning schedules are not recurrence rules.")
    return from_action_schedule(schedule, family_timezone)


def _describe_recurrence(recurrence, language):
    de = language.casefold().startswith("de")
    frequency = recurrence.get("frequency")
    interval = recurrence.get("interval", 1)
    names = {
        "daily": ("Tag", "day"),
        "weekly": ("Woche", "week"),
        "monthly": ("Monat", "month"),
        "quarterly": ("Quartal", "quarter"),
        "yearly": ("Jahr", "year"),
    }
    if frequency == "once":
        return ("Einmal am " if de else "Once on ") + recurrence["date"]
    unit = names.get(frequency, (frequency, frequency))[0 if de else 1]
    if interval == 1:
        base = f"Jeden {unit}" if de else f"Every {unit}"
    else:
        plural = {"Tag": "Tage", "Woche": "Wochen", "Monat": "Monate", "Quartal": "Quartale", "Jahr": "Jahre"}.get(unit, unit + "s") if de else unit + "s"
        base = f"Alle {interval} {plural}" if de else f"Every {interval} {plural}"

    weekday_names = {
        "MO": ("Montag", "Monday"), "TU": ("Dienstag", "Tuesday"), "WE": ("Mittwoch", "Wednesday"),
        "TH": ("Donnerstag", "Thursday"), "FR": ("Freitag", "Friday"), "SA": ("Samstag", "Saturday"), "SU": ("Sonntag", "Sunday"),
    }
    ordinal_names = {
        -1: ("letzten", "last"), 1: ("ersten", "first"), 2: ("zweiten", "second"),
        3: ("dritten", "third"), 4: ("vierten", "fourth"), 5: ("fünften", "fifth"),
    }
    details = []
    if recurrence.get("nth_weekdays"):
        for item in recurrence["nth_weekdays"]:
            ordinal = ordinal_names[item["ordinal"]][0 if de else 1]
            weekday = weekday_names[item["weekday"]][0 if de else 1]
            details.append(f"{ordinal} {weekday}" if de else f"{ordinal} {weekday}")
    elif recurrence.get("weekdays"):
        details.extend(weekday_names[item][0 if de else 1] for item in recurrence["weekdays"])
    if recurrence.get("months"):
        month_names_de = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
        month_names_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        month_names = month_names_de if de else month_names_en
        details.append(", ".join(month_names[item - 1] for item in recurrence["months"]))
    return base + ((": " if de else ": ") + ", ".join(details) if details else "")


def describe_scheduling_rule(rule, family_timezone, language="de"):
    """Create a stable human-readable summary from the canonical rule."""
    normalized = normalize_scheduling_rule(rule, family_timezone)
    text = _describe_recurrence(normalized["recurrence"], language)
    bounds = normalized.get("bounds", {})
    suffixes = []
    if bounds.get("start_on"):
        suffixes.append(("ab " if language.startswith("de") else "from ") + bounds["start_on"])
    if bounds.get("end_on"):
        suffixes.append(("bis " if language.startswith("de") else "until ") + bounds["end_on"])
    if bounds.get("count"):
        suffixes.append((f"{bounds['count']} Vorkommen" if language.startswith("de") else f"{bounds['count']} occurrences"))
    if normalized.get("pauses"):
        suffixes.append((f"{len(normalized['pauses'])} Pause(n)" if language.startswith("de") else f"{len(normalized['pauses'])} pause(s)"))
    return text + (" · " + " · ".join(suffixes) if suffixes else "")


def _is_paused(day, pauses):
    return any(date.fromisoformat(item["start_on"]) <= day <= date.fromisoformat(item["end_on"]) for item in pauses)


def preview_occurrence_dates(rule, family_timezone, after=None, limit=5):
    """Return bounded occurrence dates for editor/API previews.

    Explicit exclusions win over recurrence/includes. Pauses suspend occurrences;
    explicit includes add dates but do not bypass a pause or exclusion.
    """
    normalized = normalize_scheduling_rule(rule, family_timezone)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_PREVIEW:
        raise ValueError(f"Preview limit must be between 1 and {MAX_PREVIEW}.")
    after_day = _iso_date(after, "after") if isinstance(after, str) else after
    if after_day is not None and not isinstance(after_day, date):
        raise ValueError("after must be a date or ISO date.")

    anchor = date.fromisoformat(normalized["anchor_date"])
    bounds = normalized.get("bounds", {})
    start = max(anchor, date.fromisoformat(bounds["start_on"])) if bounds.get("start_on") else anchor
    end = date.fromisoformat(bounds["end_on"]) if bounds.get("end_on") else None
    max_count = bounds.get("count")
    generation_start = start if max_count else max(start, after_day or start)
    schedule = {
        "anchor_date": normalized["anchor_date"],
        "recurrence": normalized["recurrence"],
    }
    base = iter(_days(schedule, generation_start))
    includes = iter(date.fromisoformat(item) for item in normalized.get("include_dates", []) if date.fromisoformat(item) >= generation_start)
    next_base = next(base, None)
    next_include = next(includes, None)
    excluded = set(normalized.get("exclude_dates", []))
    excluded_weekdays = set(normalized.get("excluded_weekdays", []))
    skipped_exceptions = {item["date"] for item in normalized.get("exceptions", []) if item.get("kind") == "skip"}
    pauses = normalized.get("pauses", [])
    accepted = 0
    result = []
    last = None

    while next_base is not None or next_include is not None:
        candidates = [item for item in (next_base, next_include) if item is not None]
        day = min(candidates)
        if next_base == day:
            next_base = next(base, None)
        if next_include == day:
            next_include = next(includes, None)
        if day == last:
            continue
        last = day
        if end and day > end:
            break
        if day.isoformat() in excluded or day.isoformat() in skipped_exceptions or WEEKDAYS[day.weekday()] in excluded_weekdays or _is_paused(day, pauses):
            continue
        accepted += 1
        if max_count and accepted > max_count:
            break
        if after_day is not None and day < after_day:
            continue
        result.append(day.isoformat())
        if len(result) >= limit:
            break
    return result
