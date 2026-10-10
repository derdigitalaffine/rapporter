from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
from django.db import transaction
from django.utils import timezone

from . import integrations as integration_core
from .models import FamilyEvent, IntegrationSource

ICS_LOOKBACK_DAYS = 366
ICS_LOOKAHEAD_DAYS = 1095
VALID_RRULE_FREQUENCIES = {
    "SECONDLY",
    "MINUTELY",
    "HOURLY",
    "DAILY",
    "WEEKLY",
    "MONTHLY",
    "YEARLY",
}


def _validate_raw_rrules(raw: bytes):
    """Reject recurrence rules that icalendar may otherwise silently discard."""
    text = raw.decode("utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    logical_lines = []
    for physical_line in text.split("\n"):
        if physical_line.startswith((" ", "\t")) and logical_lines:
            logical_lines[-1] += physical_line[1:]
        else:
            logical_lines.append(physical_line)

    for line in logical_lines:
        name, separator, value = line.partition(":")
        if not separator or name.upper() != "RRULE":
            continue
        frequency = None
        for part in value.split(";"):
            key, has_value, candidate = part.partition("=")
            if has_value and key.upper() == "FREQ":
                frequency = candidate.upper()
                break
        if frequency not in VALID_RRULE_FREQUENCIES:
            raise ValueError("Die ICS-Wiederholungsregel ist ungültig.")


def _family_zone(source: IntegrationSource):
    try:
        return ZoneInfo(source.family.timezone or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _decoded(component, key, default=None):
    try:
        return component.decoded(key, default)
    except (KeyError, ValueError, TypeError):
        return default


def _is_all_day(value):
    return isinstance(value, date) and not isinstance(value, datetime)


def _aware(value, zone):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if _is_all_day(value):
        value = datetime.combine(value, time.min)
    if timezone.is_naive(value):
        return value.replace(tzinfo=zone)
    return value


def _local_date(value, zone):
    if _is_all_day(value):
        return value
    aware = _aware(value, zone)
    return aware.astimezone(zone).date() if aware else None


def _property_values(component, name):
    raw = component.get(name)
    if not raw:
        return []
    properties = raw if isinstance(raw, list) else [raw]
    values = []
    for prop in properties:
        entries = getattr(prop, "dts", None)
        if entries is not None:
            values.extend(item.dt for item in entries)
            continue
        value = getattr(prop, "dt", None)
        if value is not None:
            values.append(value)
    return values


def _event_duration(component, start_raw, zone):
    end_raw = _decoded(component, "dtend")
    if end_raw is not None:
        return max(_aware(end_raw, zone) - _aware(start_raw, zone), timedelta(0))
    duration = _decoded(component, "duration")
    if isinstance(duration, timedelta):
        return max(duration, timedelta(0))
    return timedelta(days=1) if _is_all_day(start_raw) else timedelta(0)


def _occurrence_key(value, zone, *, all_day=False):
    if all_day:
        local = _local_date(value, zone)
        return local.isoformat() if local else ""
    aware = _aware(value, zone)
    return aware.astimezone(dt_timezone.utc).isoformat() if aware else ""


def _external_id(uid, occurrence_key=None):
    value = uid if occurrence_key is None else f"{uid}::{occurrence_key}"
    if len(value) <= 180:
        return value
    digest = sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{value[:150]}::{digest}"


def _rrule_occurrences(component, start_raw, zone, window_start, window_end):
    if "RRULE" not in component:
        return []
    raw = component.get("rrule")

    local_rule = _is_all_day(start_raw) or (
        isinstance(start_raw, datetime) and timezone.is_naive(start_raw)
    )
    if _is_all_day(start_raw):
        rule_start = datetime.combine(start_raw, time.min)
    else:
        rule_start = start_raw
    if local_rule:
        rule_window_start = window_start.astimezone(zone).replace(tzinfo=None)
        rule_window_end = window_end.astimezone(zone).replace(tzinfo=None)
    else:
        rule_window_start = window_start
        rule_window_end = window_end

    try:
        rule_text = raw.to_ical().decode("utf-8") if raw is not None else ""
        if not rule_text.strip():
            raise ValueError("Leere Wiederholungsregel")
        rule = rrulestr(rule_text, dtstart=rule_start)
        values = list(
            rule.between(rule_window_start, rule_window_end, inc=True)
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Die ICS-Wiederholungsregel ist ungültig.") from exc

    if not local_rule:
        return values
    return [
        value.replace(tzinfo=zone)
        if timezone.is_naive(value)
        else value.astimezone(zone)
        for value in values
    ]


def _rdate_occurrences(component, zone, default_duration):
    values = []
    for raw_value in _property_values(component, "rdate"):
        duration = default_duration
        start_raw = raw_value
        if isinstance(raw_value, tuple) and len(raw_value) == 2:
            start_raw, period_end = raw_value
            if isinstance(period_end, timedelta):
                duration = max(period_end, timedelta(0))
            else:
                duration = max(
                    _aware(period_end, zone) - _aware(start_raw, zone),
                    timedelta(0),
                )
        values.append((start_raw, duration))
    return values


def _event_defaults(
    source,
    component,
    start,
    end,
    *,
    all_day,
    recurring,
    recurrence_key,
):
    config = source.config or {}
    event_type = (
        "waste.collection"
        if source.kind == IntegrationSource.Kind.WASTE
        else config.get("event_type", "calendar.event")
    )
    payload = {
        "location": str(component.get("location", "")),
        "description": str(component.get("description", "")),
        "provider": config.get("provider") or source.name or "ICS/iCal",
        "all_day": all_day,
        "recurring": recurring,
    }
    if all_day:
        zone = _family_zone(source)
        start_date = start.astimezone(zone).date()
        end_date = end.astimezone(zone).date() if end else start_date + timedelta(days=1)
        payload.update(
            {
                "date_start": start_date.isoformat(),
                "date_end_exclusive": end_date.isoformat(),
            }
        )
    if recurrence_key:
        payload["recurrence_id"] = recurrence_key
    return {
        "type": event_type,
        "title": str(component.get("summary", "Termin")) or "Termin",
        "starts_at": start,
        "ends_at": end,
        "actionable": source.kind == IntegrationSource.Kind.WASTE,
        "payload": payload,
    }


def _upsert_projection(source, external_id, defaults):
    queryset = FamilyEvent.objects.filter(
        family=source.family,
        source=source,
        external_id=external_id,
    ).order_by("id")
    event = queryset.first()
    if event:
        for key, value in defaults.items():
            setattr(event, key, value)
        event.save(update_fields=[*defaults.keys(), "updated_at"])
        queryset.exclude(pk=event.pk).delete()
        return event
    return FamilyEvent.objects.create(
        family=source.family,
        source=source,
        external_id=external_id,
        **defaults,
    )


def _generated_uid(component):
    parts = [
        str(component.get("summary", "")),
        str(_decoded(component, "dtstart", "")),
        str(_decoded(component, "dtend", "")),
        str(component.get("location", "")),
        str(_decoded(component, "recurrence-id", "")),
    ]
    return f"generated:{sha256('|'.join(parts).encode('utf-8')).hexdigest()[:32]}"


def _materialize_group(source, uid, components, window_start, window_end, zone):
    masters = [item for item in components if item.get("recurrence-id") is None]
    exceptions = [item for item in components if item.get("recurrence-id") is not None]
    master = masters[0] if masters else None
    rows = []

    if master is None:
        for item in exceptions:
            if str(item.get("status", "")).upper() == "CANCELLED":
                continue
            start_raw = _decoded(item, "dtstart") or _decoded(item, "recurrence-id")
            if start_raw is None:
                continue
            all_day = _is_all_day(start_raw)
            start = _aware(start_raw, zone)
            if not (window_start <= start <= window_end):
                continue
            duration = _event_duration(item, start_raw, zone)
            key = _occurrence_key(
                _decoded(item, "recurrence-id") or start_raw,
                zone,
                all_day=all_day,
            )
            rows.append(
                (
                    _external_id(uid, key),
                    _event_defaults(
                        source,
                        item,
                        start,
                        start + duration,
                        all_day=all_day,
                        recurring=True,
                        recurrence_key=key,
                    ),
                )
            )
        return rows

    if str(master.get("status", "")).upper() == "CANCELLED":
        return []

    start_raw = _decoded(master, "dtstart")
    if start_raw is None:
        return []

    all_day = _is_all_day(start_raw)
    start = _aware(start_raw, zone)
    duration = _event_duration(master, start_raw, zone)
    exdates = {
        _occurrence_key(value, zone, all_day=all_day)
        for value in _property_values(master, "exdate")
    }
    rdates = _rdate_occurrences(master, zone, duration)
    has_rrule = "RRULE" in master
    recurring = has_rrule or bool(rdates or exceptions)

    if not recurring:
        return [
            (
                _external_id(uid),
                _event_defaults(
                    source,
                    master,
                    start,
                    start + duration,
                    all_day=all_day,
                    recurring=False,
                    recurrence_key="",
                ),
            )
        ]

    occurrences = {}
    for value in _rrule_occurrences(master, start_raw, zone, window_start, window_end):
        key = _occurrence_key(value, zone, all_day=all_day)
        occurrences[key] = (value, master, all_day, duration)

    if not has_rrule and window_start <= start <= window_end:
        key = _occurrence_key(start_raw, zone, all_day=all_day)
        occurrences[key] = (start, master, all_day, duration)

    for rdate_raw, rdate_duration in rdates:
        rdate_start = _aware(rdate_raw, zone)
        if window_start <= rdate_start <= window_end:
            rdate_all_day = _is_all_day(rdate_raw) or all_day
            key = _occurrence_key(rdate_raw, zone, all_day=all_day)
            occurrences[key] = (rdate_start, master, rdate_all_day, rdate_duration)

    for key in exdates:
        occurrences.pop(key, None)

    for item in exceptions:
        recurrence_raw = _decoded(item, "recurrence-id")
        if recurrence_raw is None:
            continue
        key = _occurrence_key(recurrence_raw, zone, all_day=all_day)
        if str(item.get("status", "")).upper() == "CANCELLED":
            occurrences.pop(key, None)
            continue

        exception_start_raw = _decoded(item, "dtstart") or recurrence_raw
        exception_start = _aware(exception_start_raw, zone)
        if not (window_start <= exception_start <= window_end):
            occurrences.pop(key, None)
            continue

        exception_all_day = _is_all_day(exception_start_raw)
        exception_duration = _event_duration(item, exception_start_raw, zone)
        occurrences[key] = (
            exception_start,
            item,
            exception_all_day,
            exception_duration,
        )

    for key, (
        occurrence_start,
        component,
        occurrence_all_day,
        occurrence_duration,
    ) in sorted(occurrences.items()):
        rows.append(
            (
                _external_id(uid, key),
                _event_defaults(
                    source,
                    component,
                    occurrence_start,
                    occurrence_start + occurrence_duration,
                    all_day=occurrence_all_day,
                    recurring=True,
                    recurrence_key=key,
                ),
            )
        )
    return rows


def sync_ics_projection(source: IntegrationSource):
    config = source.config or {}
    snapshot = config.get("ics_content")
    if snapshot:
        raw = snapshot.encode("utf-8")
    else:
        if not source.endpoint:
            raise ValueError(
                "Bitte eine öffentliche HTTPS-iCal/ICS-URL oder eine ICS-Datei angeben."
            )
        raw = integration_core._get(source.endpoint).content

    _validate_raw_rrules(raw)
    calendar = integration_core.validate_ics_bytes(raw)
    zone = _family_zone(source)
    now = timezone.now().astimezone(zone)
    window_start = now - timedelta(days=ICS_LOOKBACK_DAYS)
    window_end = now + timedelta(days=ICS_LOOKAHEAD_DAYS)

    groups = {}
    for component in calendar.walk("VEVENT"):
        uid = str(component.get("uid", "")).strip() or _generated_uid(component)
        groups.setdefault(uid, []).append(component)

    rows = {}
    for uid, components in groups.items():
        for external_id, defaults in _materialize_group(
            source,
            uid,
            components,
            window_start,
            window_end,
            zone,
        ):
            rows[external_id] = defaults

    active_ids = list(rows)
    with transaction.atomic():
        IntegrationSource.objects.select_for_update().only("pk").get(pk=source.pk)
        for external_id, defaults in rows.items():
            _upsert_projection(source, external_id, defaults)
        stale = FamilyEvent.objects.filter(source=source)
        if active_ids:
            stale = stale.exclude(external_id__in=active_ids)
        stale.delete()
        return integration_core._finish(source, len(active_ids))
