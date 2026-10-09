import ipaddress
import socket
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urljoin, urlparse

import requests
from icalendar import Calendar
from django.utils import timezone

from .models import FamilyEvent, InboxItem, IntegrationSource, ShoppingList, ShoppingItem, Task, TaskList

UA = {"User-Agent": "fam-uh-le/1.0 (+family-dashboard)"}
DWD_WARNINGS = "https://www.dwd.de/DWD/warnungen/warnapp/json/warnings.json"
NINA_DASHBOARD = "https://warnung.bund.de/api31/dashboard/{ars}.json"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
TELEGRAM = "https://api.telegram.org/bot{token}/{method}"
MAX_ICS_UPLOAD_BYTES = 2 * 1024 * 1024


def _safe_public_https(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Nur öffentliche HTTPS-Endpunkte sind erlaubt.")
    for info in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Private oder lokale Netzwerkziele sind für externe Integrationen gesperrt.")


def _get(url, *, params=None, timeout=15):
    current = url
    for _ in range(4):
        _safe_public_https(current)
        response = requests.get(current, params=params, timeout=timeout, headers=UA, allow_redirects=False)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            if not location:
                raise ValueError("Integration lieferte eine ungültige Weiterleitung.")
            current = urljoin(current, location)
            params = None
            continue
        response.raise_for_status()
        return response
    raise ValueError("Zu viele Weiterleitungen beim Abruf der Integration.")


def _finish(source, count):
    source.last_synced_at = timezone.now()
    source.save(update_fields=["last_synced_at", "updated_at"])
    return count


def _aware(value):
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not hasattr(value, "hour"):
        value = datetime.combine(value, datetime.min.time())
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value


def validate_ics_bytes(content):
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content or b"")
    if not raw:
        raise ValueError("Die ICS-Datei ist leer.")
    if len(raw) > MAX_ICS_UPLOAD_BYTES:
        raise ValueError("Die ICS-Datei darf höchstens 2 MB groß sein.")
    try:
        calendar = Calendar.from_ical(raw)
    except Exception as exc:
        raise ValueError("Die Datei ist kein gültiger ICS/iCal-Kalender.") from exc
    if getattr(calendar, "name", "") != "VCALENDAR":
        raise ValueError("Die Datei enthält keinen gültigen VCALENDAR-Kalender.")
    return calendar


def normalize_ics_upload(content):
    raw = bytes(content or b"")
    validate_ics_bytes(raw)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Die ICS-Datei muss UTF-8-kodiert sein.") from exc


def sync_ics(source: IntegrationSource):
    config = source.config or {}
    snapshot = config.get("ics_content")
    if snapshot:
        raw = snapshot.encode("utf-8")
    else:
        if not source.endpoint:
            raise ValueError("Bitte eine öffentliche HTTPS-iCal/ICS-URL oder eine ICS-Datei angeben.")
        raw = _get(source.endpoint).content
    calendar = validate_ics_bytes(raw)
    count = 0
    for component in calendar.walk("VEVENT"):
        uid = str(component.get("uid", ""))
        title = str(component.get("summary", "Termin"))
        start = _aware(component.decoded("dtstart", None))
        end = _aware(component.decoded("dtend", None))
        external_id = uid or f"{title}:{start}"
        event_type = "waste.collection" if source.kind == IntegrationSource.Kind.WASTE else config.get("event_type", "calendar.event")
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id=external_id,
            defaults={
                "type": event_type,
                "title": title,
                "starts_at": start,
                "ends_at": end,
                "actionable": source.kind == IntegrationSource.Kind.WASTE,
                "payload": {
                    "location": str(component.get("location", "")),
                    "description": str(component.get("description", "")),
                    "provider": config.get("provider", "ICS/iCal"),
                },
            },
        )
        count += 1
    return _finish(source, count)


def sync_dwd(source: IntegrationSource):
    data = _get(DWD_WARNINGS).json()
    needle = str(source.config.get("region", "Kaiserslautern")).lower()
    count = 0
    active_ids = []
    for cell_id, warnings in (data.get("warnings") or {}).items():
        for warning in warnings:
            region = str(warning.get("regionName", ""))
            if needle not in region.lower():
                continue
            external_id = f"dwd:{warning.get('event')}:{warning.get('start')}:{cell_id}"
            active_ids.append(external_id)
            FamilyEvent.objects.update_or_create(
                family=source.family,
                source=source,
                external_id=external_id,
                defaults={
                    "type": "weather.warning",
                    "title": warning.get("headline") or warning.get("event") or "DWD-Warnung",
                    "starts_at": datetime.fromtimestamp(warning["start"] / 1000, tz=dt_timezone.utc) if warning.get("start") else timezone.now(),
                    "ends_at": datetime.fromtimestamp(warning["end"] / 1000, tz=dt_timezone.utc) if warning.get("end") else None,
                    "actionable": True,
                    "payload": {
                        "region": region,
                        "level": warning.get("level"),
                        "description": warning.get("description", ""),
                        "instruction": warning.get("instruction", ""),
                        "provider": "DWD",
                    },
                },
            )
            count += 1
    FamilyEvent.objects.filter(source=source, type="weather.warning").exclude(external_id__in=active_ids).delete()
    return _finish(source, count)


def sync_nina(source: IntegrationSource):
    ars = str(source.config.get("ars") or "073120000000")
    data = _get(NINA_DASHBOARD.format(ars=ars)).json()
    count = 0
    active_ids = []
    for item in data:
        payload = item.get("payload") or {}
        details = payload.get("data") or {}
        external = str(payload.get("id") or item.get("id") or "")
        if not external:
            continue
        external_id = f"nina:{external}"
        active_ids.append(external_id)
        title = details.get("headline") or ((payload.get("i18nTitle") or {}).get("de")) or "Amtliche Warnung"
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id=external_id,
            defaults={
                "type": "public.warning",
                "title": title,
                "starts_at": _aware(payload.get("sent")) or timezone.now(),
                "ends_at": None,
                "actionable": True,
                "payload": {
                    "provider": details.get("provider") or "NINA/BBK",
                    "severity": details.get("severity"),
                    "message_type": details.get("msgType"),
                    "ars": ars,
                },
            },
        )
        count += 1
    FamilyEvent.objects.filter(source=source, type="public.warning").exclude(external_id__in=active_ids).delete()
    return _finish(source, count)


def sync_weather(source: IntegrationSource):
    lat = source.config.get("latitude", 49.44)
    lon = source.config.get("longitude", 7.77)
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": source.family.timezone,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
        "forecast_days": 7,
    }
    data = _get(OPEN_METEO, params=params).json()
    daily = data.get("daily") or {}
    count = 0
    for i, day in enumerate(daily.get("time", [])):
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id=f"weather:{day}",
            defaults={
                "type": "weather.forecast",
                "title": f"Wetter {day}",
                "starts_at": _aware(day),
                "ends_at": None,
                "actionable": False,
                "payload": {
                    "provider": "Open-Meteo",
                    "weather_code": (daily.get("weather_code") or [None] * 7)[i],
                    "temp_max": (daily.get("temperature_2m_max") or [None] * 7)[i],
                    "temp_min": (daily.get("temperature_2m_min") or [None] * 7)[i],
                    "rain_probability": (daily.get("precipitation_probability_max") or [None] * 7)[i],
                    "wind_max": (daily.get("wind_speed_10m_max") or [None] * 7)[i],
                },
            },
        )
        count += 1
    return _finish(source, count)


def sync_telegram(source: IntegrationSource):
    token = source.config.get("bot_token")
    if not token:
        raise ValueError("Telegram Bot-Token fehlt.")
    offset = int(source.config.get("offset", 0))
    result = _get(TELEGRAM.format(token=token, method="getUpdates"), params={"timeout": 0, "offset": offset}).json()
    if not result.get("ok"):
        raise ValueError(result.get("description") or "Telegram API Fehler")
    count = 0
    max_offset = offset
    allowed_chat = str(source.config.get("chat_id") or "")
    for update in result.get("result", []):
        max_offset = max(max_offset, int(update["update_id"]) + 1)
        msg = update.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        if allowed_chat and chat_id != allowed_chat:
            continue
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            continue
        sender = (msg.get("from") or {}).get("first_name") or "Telegram"
        if text.lower().startswith(("/todo ", "/task ")):
            task_list, _ = TaskList.objects.get_or_create(family=source.family, name="Allgemein", defaults={"icon": "list-check"})
            Task.objects.create(family=source.family, task_list=task_list, title=text.split(" ", 1)[1], source="telegram")
        elif text.lower().startswith(("/buy ", "/einkauf ")):
            shopping = ShoppingList.objects.filter(family=source.family, archived=False).first() or ShoppingList.objects.create(family=source.family, name="Einkauf")
            ShoppingItem.objects.create(shopping_list=shopping, name=text.split(" ", 1)[1])
        else:
            already = InboxItem.objects.filter(family=source.family, source="telegram", parsed__telegram_update_id=update["update_id"]).exists()
            if not already:
                InboxItem.objects.create(family=source.family, source="telegram", title=sender, body=text, parsed={"telegram_update_id": update["update_id"], "chat_id": chat_id})
        count += 1
    cfg = dict(source.config)
    cfg["offset"] = max_offset
    source.config = cfg
    source.save(update_fields=["config", "updated_at"])
    return _finish(source, count)


def sync_source(source: IntegrationSource):
    adapter = source.config.get("adapter")
    if source.kind in {IntegrationSource.Kind.ICS, IntegrationSource.Kind.WASTE} or adapter in {"ics", "waste_kl_city", "waste_kl_county"}:
        return sync_ics(source)
    if source.kind == IntegrationSource.Kind.WARNING and adapter == "dwd":
        return sync_dwd(source)
    if source.kind == IntegrationSource.Kind.WARNING and adapter == "nina":
        return sync_nina(source)
    if source.kind == IntegrationSource.Kind.WEATHER or adapter == "weather":
        return sync_weather(source)
    if source.kind == IntegrationSource.Kind.MESSENGER and adapter == "telegram":
        return sync_telegram(source)
    raise ValueError("Für diese Integration ist noch kein Adapter konfiguriert.")


INTEGRATION_CATALOG = [
    {"id": "waste_kl_city", "kind": "waste", "name": "Müllkalender Stadt Kaiserslautern", "description": "Heruntergeladene ICS-Datei der Stadtbildpflege importieren.", "help_url": "https://www.kaiserslautern.de/serviceportal/onlineservice/index.html.de/index.html?lang=de", "fields": [{"key": "ics_file", "label": "ICS-Datei", "type": "file", "accept": ".ics,text/calendar", "required": True}], "defaults": {"adapter": "waste_kl_city", "provider": "Stadtbildpflege Kaiserslautern", "event_type": "waste.collection", "static_ics": True}},
    {"id": "waste_kl_county", "kind": "waste", "name": "Müllkalender Landkreis Kaiserslautern", "description": "Adressbezogenen Export des offiziellen interaktiven Landkreis-Kalenders verbinden.", "help_url": "https://abfallapp.softwareentwicklung-roth.de/web/KL/de/kalender", "fields": [{"key": "endpoint", "label": "iCal/ICS-URL", "type": "url", "required": True}], "defaults": {"adapter": "waste_kl_county", "provider": "Landkreis Kaiserslautern", "event_type": "waste.collection"}},
    {"id": "ics", "kind": "ics", "name": "Kalender (ICS/iCal)", "description": "Öffentlichen HTTPS-Kalender abonnieren.", "fields": [{"key": "endpoint", "label": "ICS-URL", "type": "url", "required": True}], "defaults": {"adapter": "ics"}},
    {"id": "dwd", "kind": "warning", "name": "DWD Wetterwarnungen", "description": "Amtliche Wetterwarnungen nach Region.", "fields": [{"key": "region", "label": "Region", "type": "text", "default": "Kaiserslautern"}], "defaults": {"adapter": "dwd", "region": "Kaiserslautern"}},
    {"id": "nina_city", "kind": "warning", "name": "NINA · Stadt Kaiserslautern", "description": "Amtliche Bevölkerungsschutzwarnungen für die kreisfreie Stadt.", "fields": [], "defaults": {"adapter": "nina", "ars": "073120000000"}},
    {"id": "nina_county", "kind": "warning", "name": "NINA · Landkreis Kaiserslautern", "description": "Amtliche Bevölkerungsschutzwarnungen für den Landkreis.", "fields": [], "defaults": {"adapter": "nina", "ars": "073350000000"}},
    {"id": "weather", "kind": "weather", "name": "7-Tage-Wetter", "description": "Wettervorhersage für Kaiserslautern oder eigene Koordinaten.", "fields": [{"key": "latitude", "label": "Breitengrad", "type": "number", "default": 49.44}, {"key": "longitude", "label": "Längengrad", "type": "number", "default": 7.77}], "defaults": {"adapter": "weather", "latitude": 49.44, "longitude": 7.77}},
    {"id": "telegram", "kind": "messenger", "name": "Telegram Bot", "description": "Nachrichten als Inbox, /todo als Aufgabe und /buy als Einkauf übernehmen.", "fields": [{"key": "bot_token", "label": "Bot Token", "type": "password", "required": True}, {"key": "chat_id", "label": "Chat-ID (optional)", "type": "text"}], "defaults": {"adapter": "telegram"}},
]
