"""CalDAV adapter into canonical FamilyEvent rows.

The remote server performs date filtering through RFC 4791 calendar-query.
FamilyEvent stays canonical. Private remote href/ETag identity lives in
CalDavEventBinding and never enters API-visible event payloads.
"""
import hashlib
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q
from django.utils import timezone
from icalendar import Calendar, Event

from .caldav_discovery import CALDAV, DAV, CalDavDiscoveryError, _parse_xml
from .caldav_models import CalDavConnection, CalDavEventBinding
from .caldav_secrets import decrypt_credentials, decrypt_value, encrypt_value
from .caldav_transport import safe_request
from .calendar_recurrence import recurrence_dict
from .models import FamilyEvent, IntegrationSource


class CalDavConflictError(ValueError):
    pass


def _zone(family):
    try:
        return ZoneInfo(family.timezone or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _utc_stamp(value):
    return value.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _header(headers, name):
    target = name.casefold()
    for key, value in (headers or {}).items():
        if str(key).casefold() == target:
            return str(value)
    return ""


def calendar_query_body(start, end):
    return f'''<?xml version="1.0" encoding="utf-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop><d:getetag/><c:calendar-data/></d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
        <c:time-range start="{_utc_stamp(start)}" end="{_utc_stamp(end)}"/>
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>'''.encode("utf-8")


def query_resources(connection, start, end, *, requester=safe_request):
    if not connection.calendar_href:
        raise CalDavDiscoveryError("caldav_calendar_not_selected")
    credentials = decrypt_credentials(connection.credentials_encrypted)
    _, _, _, payload = requester(
        connection.calendar_href,
        username=credentials["username"],
        password=credentials["password"],
        method="REPORT",
        body=calendar_query_body(start, end),
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
        accepted=(207,),
    )
    root = _parse_xml(payload)
    rows = []
    for response in root.findall(f".//{{{DAV}}}response"):
        href = response.find(f"{{{DAV}}}href")
        data = response.find(f".//{{{CALDAV}}}calendar-data")
        if href is None or data is None or not (href.text or "").strip() or not (data.text or "").strip():
            continue
        etag = response.find(f".//{{{DAV}}}getetag")
        rows.append({
            "href": urljoin(connection.calendar_href, href.text.strip()),
            "etag": (etag.text or "").strip() if etag is not None else "",
            "data": data.text.encode("utf-8"),
        })
    return rows


def _aware(value, family):
    zone = _zone(family)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=zone)
    if isinstance(value, date):
        return datetime.combine(value, time.min, zone)
    return None


def parse_resource(resource, family):
    try:
        calendar = Calendar.from_ical(resource["data"])
    except Exception as exc:
        raise CalDavDiscoveryError("caldav_ical_invalid") from exc
    components = calendar.walk("VEVENT")
    if not components:
        raise CalDavDiscoveryError("caldav_event_missing")
    primary = next((row for row in components if "RECURRENCE-ID" not in row), components[0])
    uid = str(primary.get("UID") or "").strip()
    if not uid:
        uid = "href:" + hashlib.sha256(resource["href"].encode("utf-8")).hexdigest()
    recurring = len(components) > 1 or any(key in primary for key in ("RRULE", "RDATE", "EXDATE", "RECURRENCE-ID"))
    start_raw = primary.decoded("DTSTART") if primary.get("DTSTART") else None
    end_raw = primary.decoded("DTEND") if primary.get("DTEND") else None
    start = _aware(start_raw, family)
    end = _aware(end_raw, family)
    all_day = isinstance(start_raw, date) and not isinstance(start_raw, datetime)
    if start is None:
        raise CalDavDiscoveryError("caldav_event_start_missing")
    if all_day and end is None:
        end = start + timedelta(days=1)
    payload = {"provider": "CalDAV"}
    location = str(primary.get("LOCATION") or "").strip()
    if location:
        payload["location"] = location[:500]
    if all_day:
        payload.update({
            "all_day": True,
            "date_start": start_raw.isoformat(),
            "date_end_exclusive": (end_raw if isinstance(end_raw, date) else (start_raw + timedelta(days=1))).isoformat(),
        })
    return {
        "uid": uid[:255],
        "title": str(primary.get("SUMMARY") or "Kalendertermin")[:200],
        "starts_at": start,
        "ends_at": end,
        "payload": payload,
        "recurring": recurring,
        **resource,
    }


def _source(connection):
    source = IntegrationSource.objects.filter(
        family=connection.family,
        config__caldav_connection=str(connection.id),
    ).first()
    if source:
        changed = []
        if source.name != connection.name:
            source.name = connection.name
            changed.append("name")
        if source.enabled != connection.enabled:
            source.enabled = connection.enabled
            changed.append("enabled")
        if changed:
            source.save(update_fields=[*changed, "updated_at"])
        return source
    return IntegrationSource.objects.create(
        family=connection.family,
        kind=IntegrationSource.Kind.ICS,
        name=connection.name,
        config={"adapter": "caldav", "provider": "CalDAV", "caldav_connection": str(connection.id)},
        enabled=connection.enabled,
    )


def _external_id(connection, uid):
    digest = hashlib.sha256(f"{connection.id}:{uid}".encode("utf-8")).hexdigest()
    return f"caldav:{digest}"


def _apply_remote_to_native(binding, parsed, seen_at):
    """Apply a remote edit only when the local event has not changed too.

    If both sides changed since the last acknowledged ETag/version pair, preserve
    both sides and report a conflict. The old ETag/local_version pair remains the
    conditional-write baseline so a later PUT cannot silently overwrite remote.
    """
    event = binding.event
    if event is None:
        return False, False
    remote_changed = bool(parsed["etag"] and parsed["etag"] != binding.etag)
    local_changed = bool(binding.local_version and event.version != binding.local_version)

    binding.remote_href_encrypted = encrypt_value(parsed["href"])
    binding.last_seen_at = seen_at
    binding.remote_deleted_at = None

    if remote_changed and local_changed:
        binding.save(update_fields=["remote_href_encrypted", "last_seen_at", "remote_deleted_at", "updated_at"])
        return False, True

    if remote_changed:
        payload = dict(event.payload or {})
        if parsed["payload"].get("location"):
            payload["location"] = parsed["payload"]["location"]
        else:
            payload.pop("location", None)
        for key in ("all_day", "date_start", "date_end_exclusive"):
            if key in parsed["payload"]:
                payload[key] = parsed["payload"][key]
            else:
                payload.pop(key, None)
        event.title = parsed["title"]
        event.starts_at = parsed["starts_at"]
        event.ends_at = parsed["ends_at"]
        event.payload = payload
        event.save(update_fields=["title", "starts_at", "ends_at", "payload", "updated_at"])
        event.refresh_from_db(fields=["version"])
        binding.local_version = event.version

    if parsed["etag"]:
        binding.etag = parsed["etag"]
    binding.save(update_fields=["etag", "remote_href_encrypted", "last_seen_at", "remote_deleted_at", "local_version", "updated_at"])
    return remote_changed, False


def _upsert_imported(connection, source, parsed, seen_at):
    external_id = _external_id(connection, parsed["uid"])
    event, _ = FamilyEvent.objects.update_or_create(
        family=connection.family,
        source=source,
        external_id=external_id,
        defaults={
            "type": "calendar.event",
            "title": parsed["title"],
            "starts_at": parsed["starts_at"],
            "ends_at": parsed["ends_at"],
            "actionable": False,
            "payload": parsed["payload"],
            "is_family_event": connection.member_id is None,
        },
    )
    if connection.member_id:
        event.participants.set([connection.member_id])
    else:
        event.participants.clear()
    binding, _ = CalDavEventBinding.objects.update_or_create(
        connection=connection,
        remote_uid=parsed["uid"],
        defaults={
            "event": event,
            "remote_href_encrypted": encrypt_value(parsed["href"]),
            "etag": parsed["etag"],
            "local_version": event.version,
            "last_seen_at": seen_at,
            "remote_deleted_at": None,
        },
    )
    return binding


def pull_remote(connection, start, end):
    if connection.scope != CalDavConnection.Scope.FAMILY or not connection.family_id:
        raise CalDavDiscoveryError("caldav_family_scope_required")
    source = _source(connection)
    seen_at = timezone.now()
    imported = updated = skipped_recurring = conflicts = 0
    for resource in query_resources(connection, start, end):
        parsed = parse_resource(resource, connection.family)
        binding = CalDavEventBinding.objects.select_related("event", "event__source").filter(
            connection=connection,
            remote_uid=parsed["uid"],
        ).first()

        # event=NULL is a local-delete tombstone. Never recreate it during the
        # pull that precedes DELETE. Preserve the old ETag so DELETE remains
        # conditional and conflicts if the remote resource changed meanwhile.
        if binding and binding.event_id is None:
            binding.remote_href_encrypted = encrypt_value(parsed["href"])
            binding.last_seen_at = seen_at
            binding.save(update_fields=["remote_href_encrypted", "last_seen_at", "updated_at"])
            continue

        if parsed["recurring"]:
            skipped_recurring += 1
            if binding:
                if parsed["etag"]:
                    binding.etag = parsed["etag"]
                binding.remote_href_encrypted = encrypt_value(parsed["href"])
                binding.last_seen_at = seen_at
                binding.save(update_fields=["etag", "remote_href_encrypted", "last_seen_at", "updated_at"])
            continue

        if binding and binding.event_id and binding.event.source_id is None:
            if connection.access_mode == CalDavConnection.AccessMode.READ_WRITE:
                changed, conflict = _apply_remote_to_native(binding, parsed, seen_at)
                updated += int(changed)
                conflicts += int(conflict)
            else:
                binding.last_seen_at = seen_at
                if parsed["etag"]:
                    binding.etag = parsed["etag"]
                binding.remote_href_encrypted = encrypt_value(parsed["href"])
                binding.save(update_fields=["last_seen_at", "etag", "remote_href_encrypted", "updated_at"])
            continue

        _upsert_imported(connection, source, parsed, seen_at)
        imported += 1

    stale = CalDavEventBinding.objects.select_related("event", "event__source").filter(connection=connection).filter(
        Q(last_seen_at__lt=seen_at) | Q(last_seen_at__isnull=True)
    ).filter(
        Q(event__starts_at__lt=end) & (Q(event__ends_at__gt=start) | Q(event__ends_at__isnull=True, event__starts_at__gte=start))
    )
    for binding in list(stale):
        event = binding.event
        if event and event.source_id == source.id:
            binding.delete()
            event.delete()
        elif event and event.source_id is None:
            binding.remote_deleted_at = seen_at
            binding.save(update_fields=["remote_deleted_at", "updated_at"])
            conflicts += 1
    source.last_synced_at = seen_at
    source.save(update_fields=["last_synced_at", "updated_at"])
    return {"pulled": imported, "remote_updates": updated, "skipped_recurring": skipped_recurring, "conflicts": conflicts}


def _event_ical(event, uid):
    if recurrence_dict((event.payload or {}).get("recurrence")):
        raise CalDavDiscoveryError("caldav_recurring_write_unsupported")
    calendar = Calendar()
    calendar.add("prodid", "-//FamilyOS//CalDAV Sync//EN")
    calendar.add("version", "2.0")
    component = Event()
    component.add("uid", uid)
    component.add("dtstamp", timezone.now().astimezone(dt_timezone.utc))
    component.add("summary", event.title)
    payload = event.payload if isinstance(event.payload, dict) else {}
    if payload.get("all_day") and payload.get("date_start"):
        try:
            start = date.fromisoformat(payload["date_start"])
            end = date.fromisoformat(payload.get("date_end_exclusive") or "") if payload.get("date_end_exclusive") else start + timedelta(days=1)
        except ValueError:
            start = event.starts_at.astimezone(_zone(event.family)).date()
            end = start + timedelta(days=1)
        component.add("dtstart", start)
        component.add("dtend", max(start + timedelta(days=1), end))
    else:
        component.add("dtstart", event.starts_at)
        if event.ends_at:
            component.add("dtend", event.ends_at)
    location = payload.get("location")
    if isinstance(location, str) and location.strip():
        component.add("location", location.strip()[:500])
    calendar.add_component(component)
    return calendar.to_ical()


def _write_binding(connection, event, binding=None):
    if connection.access_mode != CalDavConnection.AccessMode.READ_WRITE:
        raise CalDavDiscoveryError("caldav_read_only")
    if recurrence_dict((event.payload or {}).get("recurrence")):
        raise CalDavDiscoveryError("caldav_recurring_write_unsupported")
    credentials = decrypt_credentials(connection.credentials_encrypted)
    uid = binding.remote_uid if binding else f"familyos-{event.pk}@familyos"
    href = decrypt_value(binding.remote_href_encrypted) if binding else urljoin(
        connection.calendar_href.rstrip("/") + "/", f"familyos-{event.pk}.ics"
    )
    headers = {"Content-Type": "text/calendar; charset=utf-8"}
    if binding and binding.etag:
        headers["If-Match"] = binding.etag
    else:
        headers["If-None-Match"] = "*"
    _, status, response_headers, _ = safe_request(
        href,
        username=credentials["username"],
        password=credentials["password"],
        method="PUT",
        body=_event_ical(event, uid),
        headers=headers,
        accepted=(201, 204, 412),
    )
    if status == 412:
        raise CalDavConflictError("caldav_etag_conflict")
    etag = _header(response_headers, "ETag")
    if not etag:
        _, _, get_headers, _ = safe_request(
            href,
            username=credentials["username"],
            password=credentials["password"],
            method="GET",
            accepted=(200,),
        )
        etag = _header(get_headers, "ETag")
    values = {
        "event": event,
        "remote_href_encrypted": encrypt_value(href),
        "etag": etag,
        "local_version": event.version,
        "last_seen_at": timezone.now(),
        "remote_deleted_at": None,
    }
    if binding:
        for key, value in values.items():
            setattr(binding, key, value)
        binding.save(update_fields=[*values.keys(), "updated_at"])
        return binding
    return CalDavEventBinding.objects.create(connection=connection, remote_uid=uid, **values)


def _delete_tombstone(binding):
    connection = binding.connection
    credentials = decrypt_credentials(connection.credentials_encrypted)
    href = decrypt_value(binding.remote_href_encrypted)
    headers = {"If-Match": binding.etag} if binding.etag else {}
    _, status, _, _ = safe_request(
        href,
        username=credentials["username"],
        password=credentials["password"],
        method="DELETE",
        headers=headers,
        accepted=(204, 404, 412),
    )
    if status == 412:
        raise CalDavConflictError("caldav_etag_conflict")
    binding.delete()


def push_local(connection, start, end):
    if connection.access_mode != CalDavConnection.AccessMode.READ_WRITE:
        return {"pushed": 0, "deleted": 0, "skipped_recurring": 0, "conflicts": 0}
    if not connection.calendar_href:
        raise CalDavDiscoveryError("caldav_calendar_not_selected")

    pushed = deleted = skipped_recurring = conflicts = 0
    for binding in list(CalDavEventBinding.objects.filter(connection=connection, event__isnull=True)):
        try:
            _delete_tombstone(binding)
            deleted += 1
        except CalDavConflictError:
            conflicts += 1

    events = FamilyEvent.objects.filter(
        family=connection.family,
        source__isnull=True,
        external_id="",
        type="calendar.event",
        starts_at__lt=end,
    ).filter(Q(ends_at__gt=start) | Q(ends_at__isnull=True, starts_at__gte=start))
    if connection.member_id:
        events = events.filter(Q(is_family_event=True) | Q(participants=connection.member_id)).distinct()
    else:
        events = events.filter(is_family_event=True)

    for event in events:
        binding = CalDavEventBinding.objects.filter(connection=connection, event=event).first()
        if binding and binding.remote_deleted_at:
            conflicts += 1
            continue
        if recurrence_dict((event.payload or {}).get("recurrence")):
            skipped_recurring += 1
            continue
        if binding and binding.local_version == event.version:
            continue
        try:
            _write_binding(connection, event, binding)
            pushed += 1
        except CalDavConflictError:
            conflicts += 1
    return {"pushed": pushed, "deleted": deleted, "skipped_recurring": skipped_recurring, "conflicts": conflicts}


def sync_connection(connection, *, past_days=30, future_days=365):
    if not connection.enabled:
        return {"pulled": 0, "remote_updates": 0, "pushed": 0, "deleted": 0, "skipped_recurring": 0, "conflicts": 0}
    if connection.scope != CalDavConnection.Scope.FAMILY:
        raise CalDavDiscoveryError("caldav_family_scope_required")
    now = timezone.now()
    start = now - timedelta(days=max(0, int(past_days)))
    end = now + timedelta(days=max(1, int(future_days)))
    pulled = pull_remote(connection, start, end)
    pushed = push_local(connection, start, end)
    return {
        "pulled": pulled["pulled"],
        "remote_updates": pulled["remote_updates"],
        "pushed": pushed["pushed"],
        "deleted": pushed["deleted"],
        "skipped_recurring": pulled["skipped_recurring"] + pushed["skipped_recurring"],
        "conflicts": pulled["conflicts"] + pushed["conflicts"],
    }
