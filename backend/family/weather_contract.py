from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from .models import FamilyEvent, IntegrationSource


WEATHER_DATA_TYPES = ("weather.current", "weather.forecast")
STALE_AFTER = timedelta(hours=6)


def _family_date(event, family):
    payload_date = (event.payload or {}).get("date")
    if payload_date:
        return str(payload_date)
    if not event.starts_at:
        return ""
    try:
        zone = ZoneInfo(family.timezone or "Europe/Berlin")
    except Exception:
        zone = timezone.get_current_timezone()
    return event.starts_at.astimezone(zone).date().isoformat()


def _weather_source(family):
    sources = IntegrationSource.objects.filter(
        family=family,
        enabled=True,
        kind=IntegrationSource.Kind.WEATHER,
    ).order_by("-last_success_at", "-updated_at")
    for source in sources:
        adapter = (source.config or {}).get("adapter")
        if adapter in {"weather", "open_meteo", "open-meteo", None, ""}:
            return source
    return sources.first()


def _current_payload(event):
    if not event:
        return None
    payload = event.payload or {}
    return {
        "observed_at": event.starts_at,
        "temperature": payload.get("temperature"),
        "apparent_temperature": payload.get("apparent_temperature"),
        "weather_code": payload.get("weather_code"),
        "humidity": payload.get("humidity"),
        "precipitation": payload.get("precipitation"),
        "wind_speed": payload.get("wind_speed"),
    }


def _forecast_payload(event, family):
    payload = event.payload or {}
    return {
        "date": _family_date(event, family),
        "weather_code": payload.get("weather_code"),
        "temp_min": payload.get("temp_min"),
        "temp_max": payload.get("temp_max"),
        "apparent_temp_min": payload.get("apparent_temp_min"),
        "apparent_temp_max": payload.get("apparent_temp_max"),
        "precipitation_probability": payload.get("precipitation_probability", payload.get("rain_probability")),
        "precipitation_sum": payload.get("precipitation_sum"),
        "wind_max": payload.get("wind_max"),
        "wind_gust_max": payload.get("wind_gust_max"),
        "sunrise": payload.get("sunrise"),
        "sunset": payload.get("sunset"),
        "uv_index_max": payload.get("uv_index_max"),
    }


def _alert_payload(event):
    payload = event.payload or {}
    return {
        "id": str(event.id),
        "title": event.title,
        "starts_at": event.starts_at,
        "ends_at": event.ends_at,
        "region": payload.get("region", ""),
        "level": payload.get("level"),
        "description": payload.get("description", ""),
        "instruction": payload.get("instruction", ""),
        "provider": payload.get("provider", "DWD"),
    }


def build_weather_contract(family):
    source = _weather_source(family)
    current_event = None
    forecast_events = []
    if source:
        current_event = FamilyEvent.objects.filter(
            family=family,
            source=source,
            type="weather.current",
        ).order_by("-starts_at", "-updated_at").first()
        forecast_events = list(FamilyEvent.objects.filter(
            family=family,
            source=source,
            type="weather.forecast",
        ).order_by("starts_at", "created_at")[:7])

    now = timezone.now()
    alerts = FamilyEvent.objects.filter(
        family=family,
        type="weather.warning",
    ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now)).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now)
    ).order_by("-payload__level", "starts_at")

    last_success_at = source.last_success_at if source else None
    stale = bool(source and (
        source.last_sync_status == "error"
        or not last_success_at
        or last_success_at < now - STALE_AFTER
    ) and (current_event or forecast_events))
    config = source.config or {} if source else {}
    current_payload = current_event.payload or {} if current_event else {}
    provider = current_payload.get("provider") or ("Open-Meteo" if source else "")
    latitude = current_payload.get("latitude", config.get("latitude"))
    longitude = current_payload.get("longitude", config.get("longitude"))
    label = config.get("location_label") or config.get("label") or config.get("location") or ""

    return {
        "source": {
            "id": str(source.id) if source else None,
            "provider": provider,
            "last_success_at": last_success_at,
            "last_attempt_at": source.last_attempt_at if source else None,
            "last_sync_status": source.last_sync_status if source else "missing",
            "last_sync_error": source.last_sync_error if source and source.last_sync_status == "error" else "",
            "stale": stale,
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "label": label,
            },
        },
        "current": _current_payload(current_event),
        "days": [_forecast_payload(event, family) for event in forecast_events],
        "alerts": [_alert_payload(event) for event in alerts],
    }
