"""Validation and bounded occurrence projection for native FamilyOS calendar events."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .action_schedule import _days, local_datetime, normalize_schedule


LEGACY_RECURRENCES = {"weekly", "monthly", "yearly"}
SUPPORTED_FREQUENCIES = {"weekly", "monthly", "quarterly", "yearly"}
MAX_OCCURRENCES_PER_EVENT = 400


def family_zone(family):
    try:
        return ZoneInfo(family.timezone or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        return ZoneInfo("UTC")


def normalize_event_recurrence(value, starts_at, family_timezone):
    """Return a validated recurrence value while preserving legacy simple strings."""
    if value in (None, ""):
        return ""
    if starts_at is None:
        raise ValueError("A recurring calendar event requires a start time.")
    if isinstance(value, str):
        if value not in LEGACY_RECURRENCES:
            raise ValueError("Unsupported calendar recurrence.")
        return value
    if not isinstance(value, dict) or value.get("frequency") not in SUPPORTED_FREQUENCIES:
        raise ValueError("Unsupported calendar recurrence.")
    zone = ZoneInfo(family_timezone or "UTC")
    anchor = starts_at.astimezone(zone).date().isoformat()
    schedule = normalize_schedule(
        {
            "mode": "static",
            "anchor_date": anchor,
            "recurrence": value,
        },
        family_timezone or "UTC",
    )
    return schedule["recurrence"]


def recurrence_dict(value):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        if value not in LEGACY_RECURRENCES:
            return None
        return {"frequency": value, "interval": 1}
    if isinstance(value, dict) and value.get("frequency") in SUPPORTED_FREQUENCIES:
        return value
    return None


def project_event(event, serialized, start, end):
    """Project a native recurring master into occurrence rows for an inclusive date range."""
    payload = event.payload if isinstance(event.payload, dict) else {}
    recurrence = recurrence_dict(payload.get("recurrence"))
    if not recurrence or event.starts_at is None:
        return [serialized]

    zone = family_zone(event.family)
    master_start = event.starts_at.astimezone(zone)
    master_end = event.ends_at.astimezone(zone) if event.ends_at else None
    anchor = master_start.date()
    schedule = {"anchor_date": anchor.isoformat(), "recurrence": recurrence}
    start_clock = master_start.replace(tzinfo=None).time()
    wall_duration = None
    if master_end is not None:
        wall_duration = master_end.replace(tzinfo=None) - master_start.replace(tzinfo=None)

    base_payload = deepcopy(serialized.get("payload") or {})
    civil_span = None
    if base_payload.get("date_start"):
        try:
            civil_start = date.fromisoformat(base_payload["date_start"])
            civil_end = date.fromisoformat(base_payload.get("date_end_exclusive") or base_payload["date_start"])
            civil_span = max(1, (civil_end - civil_start).days)
        except (TypeError, ValueError):
            civil_span = None

    projected = []
    projection_start = max(start, anchor)
    for index, day in enumerate(_days(schedule, projection_start)):
        if index >= MAX_OCCURRENCES_PER_EVENT or day > end:
            break
        occurrence_start = local_datetime(day, start_clock, zone)
        occurrence_end = None
        if wall_duration is not None:
            end_naive = datetime.combine(day, start_clock) + wall_duration
            occurrence_end = local_datetime(end_naive.date(), end_naive.time(), zone)
        row = dict(serialized)
        row["starts_at"] = occurrence_start.isoformat()
        row["ends_at"] = occurrence_end.isoformat() if occurrence_end else None
        row["recurrence_master_id"] = str(event.id)
        row["recurrence_master_starts_at"] = serialized.get("starts_at")
        row["recurrence_master_ends_at"] = serialized.get("ends_at")
        row["recurrence_occurrence_date"] = day.isoformat()
        if civil_span is not None:
            row_payload = deepcopy(base_payload)
            row_payload["date_start"] = day.isoformat()
            row_payload["date_end_exclusive"] = (day + timedelta(days=civil_span)).isoformat()
            row["payload"] = row_payload
        projected.append(row)
    return projected
