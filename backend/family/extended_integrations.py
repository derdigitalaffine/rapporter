import hashlib
import ipaddress
import socket
from datetime import timedelta
from urllib.parse import urljoin, urlparse

import requests
from django.utils import timezone

from .integrations import INTEGRATION_CATALOG as LEGACY_CATALOG
from .integrations import _aware, _finish, sync_ics, sync_source as sync_legacy_source
from .models import FamilyEvent, IntegrationSource
from .oauth import refresh_access_token

UA = {"User-Agent": "fam-uh-le/1.0 (+family-dashboard)"}
GOOGLE_EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
MICROSOFT_EVENTS = "https://graph.microsoft.com/v1.0/me/calendarView"
VRN_DEPARTURES = "https://trias.vrn.de/vrn/XML_DM_REQUEST"


def _external_id(prefix, value):
    value = str(value or "")
    raw = f"{prefix}:{value}"
    if len(raw) <= 180:
        return raw
    return f"{prefix}:{hashlib.sha256(value.encode()).hexdigest()}"


def _json_get(url, *, params=None, headers=None, timeout=15):
    response = requests.get(url, params=params, headers={**UA, **(headers or {})}, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _validate_trusted_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Home-Assistant-URL muss mit http:// oder https:// beginnen.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    for info in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("Diese Home-Assistant-Adresse ist aus dem Container nicht sicher erreichbar.")
    return parsed


def _home_request(source, method, path, *, json=None):
    endpoint = (source.endpoint or "").rstrip("/")
    if not endpoint:
        raise ValueError("Home-Assistant-URL fehlt.")
    token = (source.config or {}).get("access_token")
    if not token:
        raise ValueError("Home-Assistant-Token fehlt.")
    current = f"{endpoint}/{path.lstrip('/')}"
    headers = {**UA, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for _ in range(4):
        _validate_trusted_url(current)
        response = requests.request(method, current, headers=headers, json=json, timeout=10, allow_redirects=False)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            if not location:
                raise ValueError("Home Assistant lieferte eine ungültige Weiterleitung.")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()
    raise ValueError("Zu viele Home-Assistant-Weiterleitungen.")


def sync_google_oauth(source):
    token = refresh_access_token(source, "google")
    now = timezone.now()
    data = _json_get(
        GOOGLE_EVENTS,
        params={
            "timeMin": (now - timedelta(days=30)).isoformat(),
            "timeMax": (now + timedelta(days=180)).isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 2500,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    active = []
    count = 0
    for item in data.get("items", []):
        if item.get("status") == "cancelled":
            continue
        ext = _external_id("google", item.get("id"))
        active.append(ext)
        start = item.get("start") or {}
        end = item.get("end") or {}
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id=ext,
            defaults={
                "type": "calendar.event",
                "title": item.get("summary") or "Google Kalender",
                "starts_at": _aware(start.get("dateTime") or start.get("date")),
                "ends_at": _aware(end.get("dateTime") or end.get("date")),
                "actionable": False,
                "payload": {
                    "provider": "Google Calendar",
                    "location": item.get("location", ""),
                    "description": item.get("description", ""),
                    "html_link": item.get("htmlLink", ""),
                },
            },
        )
        count += 1
    FamilyEvent.objects.filter(source=source, external_id__startswith="google:").exclude(external_id__in=active).delete()
    return _finish(source, count)


def sync_microsoft_oauth(source):
    token = refresh_access_token(source, "microsoft")
    now = timezone.now()
    data = _json_get(
        MICROSOFT_EVENTS,
        params={
            "startDateTime": (now - timedelta(days=30)).isoformat(),
            "endDateTime": (now + timedelta(days=180)).isoformat(),
            "$top": 1000,
            "$orderby": "start/dateTime",
        },
        headers={"Authorization": f"Bearer {token}", "Prefer": 'outlook.timezone="UTC"'},
    )
    active = []
    count = 0
    for item in data.get("value", []):
        if item.get("isCancelled"):
            continue
        ext = _external_id("microsoft", item.get("id"))
        active.append(ext)
        start = (item.get("start") or {}).get("dateTime")
        end = (item.get("end") or {}).get("dateTime")
        location = (item.get("location") or {}).get("displayName", "")
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id=ext,
            defaults={
                "type": "calendar.event",
                "title": item.get("subject") or "Outlook Kalender",
                "starts_at": _aware(start),
                "ends_at": _aware(end),
                "actionable": False,
                "payload": {
                    "provider": "Microsoft Outlook",
                    "location": location,
                    "web_link": item.get("webLink", ""),
                },
            },
        )
        count += 1
    FamilyEvent.objects.filter(source=source, external_id__startswith="microsoft:").exclude(external_id__in=active).delete()
    return _finish(source, count)


def sync_home_assistant(source):
    raw_ids = str((source.config or {}).get("entity_ids") or "")
    entity_ids = [x.strip() for x in raw_ids.replace("\n", ",").split(",") if x.strip()]
    if not entity_ids:
        raise ValueError("Mindestens eine Home-Assistant-Entity angeben.")
    active = []
    for entity_id in entity_ids:
        state = _home_request(source, "GET", f"api/states/{entity_id}")
        attrs = state.get("attributes") or {}
        ext = _external_id("ha", entity_id)
        active.append(ext)
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id=ext,
            defaults={
                "type": "home.state",
                "title": attrs.get("friendly_name") or entity_id,
                "starts_at": _aware(state.get("last_changed")) or timezone.now(),
                "ends_at": None,
                "actionable": True,
                "payload": {
                    "provider": "Home Assistant",
                    "entity_id": entity_id,
                    "state": state.get("state"),
                    "unit": attrs.get("unit_of_measurement"),
                    "device_class": attrs.get("device_class"),
                    "icon": attrs.get("icon"),
                    "last_changed": state.get("last_changed"),
                },
            },
        )
    FamilyEvent.objects.filter(source=source, external_id__startswith="ha:").exclude(external_id__in=active).delete()
    return _finish(source, len(active))


def home_assistant_service(source, domain, service, *, entity_id="", data=None):
    if source.kind != IntegrationSource.Kind.HOME or (source.config or {}).get("adapter") != "home_assistant":
        raise ValueError("Die gewählte Integration ist kein Home Assistant.")
    payload = dict(data or {})
    if entity_id:
        payload["entity_id"] = entity_id
    return _home_request(source, "POST", f"api/services/{domain}/{service}", json=payload)


def _find_stop_events(value):
    if isinstance(value, dict):
        if isinstance(value.get("stopEvents"), list):
            return value["stopEvents"]
        for child in value.values():
            found = _find_stop_events(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_stop_events(child)
            if found is not None:
                return found
    return None


def _first(mapping, *paths):
    for path in paths:
        value = mapping
        ok = True
        for part in path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                ok = False
                break
        if ok and value not in (None, ""):
            return value
    return None


def sync_vrn(source):
    cfg = source.config or {}
    stop_id = str(cfg.get("stop_id") or "").strip()
    if not stop_id:
        raise ValueError("VRN-Haltestellen-ID fehlt.")
    data = _json_get(
        VRN_DEPARTURES,
        params={
            "commonMacro": "dm",
            "outputFormat": "RapidJSON",
            "name_dm": stop_id,
            "type_dm": "any",
            "useRealtime": 1,
            "locationServerActive": 1,
            "coordOutputFormat": "WGS84[dd.ddddd]",
            "mode": "direct",
        },
    )
    events = _find_stop_events(data) or []
    line_filter = str(cfg.get("line") or "").strip().casefold()
    active, count = [], 0
    for item in events:
        line = str(_first(item, "transportation.number", "transportation.name", "transportation.disassembledName", "line.name") or "")
        if line_filter and line_filter not in line.casefold():
            continue
        destination = str(_first(item, "transportation.destination.name", "transportation.destination", "destination.name", "destination") or "")
        planned = _first(item, "departureTimePlanned", "departure.planned", "plannedTime")
        estimated = _first(item, "departureTimeEstimated", "departure.estimated", "estimatedTime") or planned
        start = _aware(estimated)
        planned_dt = _aware(planned)
        delay = 0
        if start and planned_dt:
            delay = max(0, round((start - planned_dt).total_seconds() / 60))
        event_id = _first(item, "properties.RealtimeTripId", "properties.tripCode", "id") or f"{line}:{destination}:{planned}"
        ext = _external_id("vrn", event_id)
        active.append(ext)
        stop_name = str(_first(item, "location.name", "stopName") or cfg.get("stop_name") or stop_id)
        title = f"{line} → {destination}".strip(" →") or "VRN-Abfahrt"
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id=ext,
            defaults={
                "type": "transit.departure",
                "title": title,
                "starts_at": start,
                "ends_at": None,
                "actionable": delay > 0,
                "payload": {
                    "provider": "VRN",
                    "line": line,
                    "destination": destination,
                    "stop": stop_name,
                    "planned": planned,
                    "estimated": estimated,
                    "delay_minutes": delay,
                },
            },
        )
        count += 1
    FamilyEvent.objects.filter(source=source, external_id__startswith="vrn:").exclude(external_id__in=active).delete()
    return _finish(source, count)


def sync_source(source):
    adapter = (source.config or {}).get("adapter")
    if adapter == "google_oauth":
        return sync_google_oauth(source)
    if adapter == "microsoft_oauth":
        return sync_microsoft_oauth(source)
    if adapter == "home_assistant":
        return sync_home_assistant(source)
    if adapter == "vrn_departures":
        return sync_vrn(source)
    if adapter in {"google_ics", "microsoft_ics", "webuntis_ics", "moodle_ics"}:
        return sync_ics(source)
    return sync_legacy_source(source)


EXTENDED_CATALOG = [
    {"id": "rlp_school_holidays", "kind": "school", "name": "Schulferien Rheinland-Pfalz", "description": "Amtliche Ferien automatisch im Kalender. Bewegliche Ferientage werden von der jeweiligen Schule festgelegt und sind nicht enthalten.", "help_url": "https://bm.rlp.de/service/ferientermine", "singleton": True, "fields": [], "defaults": {"adapter": "rlp_school_holidays", "provider": "Ministerium für Bildung Rheinland-Pfalz"}},
    {"id": "google_oauth", "kind": "ics", "name": "Google Kalender · OAuth", "description": "Google Calendar schreibgeschützt per OAuth verbinden. Keine private Kalender-URL nötig.", "oauth_provider": "google", "fields": [], "defaults": {"adapter": "google_oauth"}},
    {"id": "microsoft_oauth", "kind": "ics", "name": "Microsoft Outlook · OAuth", "description": "Outlook/Microsoft 365 Kalender schreibgeschützt per OAuth verbinden.", "oauth_provider": "microsoft", "fields": [], "defaults": {"adapter": "microsoft_oauth"}},
    {"id": "google_ics", "kind": "ics", "name": "Google Kalender · iCal", "description": "Privaten iCal-Link eines Google-Kalenders abonnieren.", "help_url": "https://support.google.com/calendar/answer/37648", "secret_endpoint": True, "fields": [{"key": "endpoint", "label": "Private iCal-Adresse", "type": "password", "required": True}], "defaults": {"adapter": "google_ics", "provider": "Google Calendar", "event_type": "calendar.event", "secret_endpoint": True}},
    {"id": "microsoft_ics", "kind": "ics", "name": "Outlook Kalender · iCal", "description": "Veröffentlichten oder privaten ICS-Link aus Outlook/Microsoft 365 abonnieren.", "help_url": "https://support.microsoft.com/office/share-your-calendar-in-outlook-on-the-web", "secret_endpoint": True, "fields": [{"key": "endpoint", "label": "ICS-Adresse", "type": "password", "required": True}], "defaults": {"adapter": "microsoft_ics", "provider": "Microsoft Outlook", "event_type": "calendar.event", "secret_endpoint": True}},
    {"id": "webuntis", "kind": "school", "name": "WebUntis Stundenplan", "description": "Privaten WebUntis-iCal-Link für Stundenplan und Unterrichtstermine abonnieren.", "help_url": "https://help.untis.at/hc/de/articles/360014979580-Wie-funktioniert-das-iCal-Kalender-Abonnement-in-WebUntis", "secret_endpoint": True, "fields": [{"key": "endpoint", "label": "WebUntis iCal-Link", "type": "password", "required": True}], "defaults": {"adapter": "webuntis_ics", "provider": "WebUntis", "event_type": "school.event", "secret_endpoint": True}},
    {"id": "moodle", "kind": "school", "name": "Moodle Kalender", "description": "Persönlichen Moodle-Kalender per exportierter iCal-URL übernehmen.", "help_url": "https://docs.moodle.org/502/en/Using_Calendar", "secret_endpoint": True, "fields": [{"key": "endpoint", "label": "Moodle iCal-URL", "type": "password", "required": True}], "defaults": {"adapter": "moodle_ics", "provider": "Moodle", "event_type": "school.event", "secret_endpoint": True}},
    {"id": "home_assistant", "kind": "home", "name": "Home Assistant", "description": "Ausgewählte Smart-Home-Entities lesen und über Wenn→Dann Services auslösen.", "help_url": "https://developers.home-assistant.io/docs/api/rest/", "fields": [{"key": "endpoint", "label": "Home-Assistant-URL", "type": "url", "required": True, "default": "http://homeassistant.local:8123"}, {"key": "access_token", "label": "Long-Lived Access Token", "type": "password", "required": True}, {"key": "entity_ids", "label": "Entities (kommagetrennt)", "type": "text", "required": True, "default": "sensor.outdoor_temperature"}], "defaults": {"adapter": "home_assistant"}},
    {"id": "vrn", "kind": "transit", "name": "VRN Abfahrten", "description": "Echtzeit-Abfahrten und Verspätungen einer VRN-Haltestelle abrufen.", "help_url": "https://opendata.vrn.de/API", "fields": [{"key": "stop_id", "label": "VRN-Haltestellen-ID", "type": "text", "required": True}, {"key": "stop_name", "label": "Anzeigename (optional)", "type": "text"}, {"key": "line", "label": "Linie filtern (optional)", "type": "text"}], "defaults": {"adapter": "vrn_departures"}},
]

INTEGRATION_CATALOG = LEGACY_CATALOG + EXTENDED_CATALOG
