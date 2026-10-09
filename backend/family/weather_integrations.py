import json
from datetime import datetime, timezone as dt_timezone

from django.utils import timezone

from .integrations import DWD_WARNINGS, OPEN_METEO, _finish, _get
from .models import FamilyEvent


DWD_JSONP_CALLBACK = "warnWetter.loadWarnings"


def _dwd_payload(response):
    try:
        return response.json()
    except ValueError:
        text = (response.text or "").strip()
        if text.startswith(DWD_JSONP_CALLBACK):
            start = text.find("(")
            end = text.rfind(")")
            if start >= len(DWD_JSONP_CALLBACK) and end > start:
                try:
                    return json.loads(text[start + 1:end])
                except json.JSONDecodeError as exc:
                    raise ValueError("DWD-Warnfeed enthält ungültige Daten.") from exc
        raise ValueError("DWD-Warnfeed hat ein unbekanntes Format.")


def sync_dwd(source):
    data = _dwd_payload(_get(DWD_WARNINGS))
    needle = str((source.config or {}).get("region", "Kaiserslautern")).strip().lower()
    count = 0
    active_ids = []
    for cell_id, warnings in (data.get("warnings") or {}).items():
        for warning in warnings:
            region = str(warning.get("regionName", ""))
            if needle and needle not in region.lower():
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


def _current_title(current):
    temperature = current.get("temperature_2m")
    if temperature is None:
        return "Wetter aktuell"
    try:
        value = f"{float(temperature):g}"
    except (TypeError, ValueError):
        value = str(temperature)
    return f"{value} °C"


def sync_weather(source):
    config = source.config or {}
    lat = config.get("latitude", 49.44)
    lon = config.get("longitude", 7.77)
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": source.family.timezone,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,precipitation,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
        "forecast_days": 7,
    }
    data = _get(OPEN_METEO, params=params).json()
    count = 0

    current = data.get("current") or {}
    if current:
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id="weather:current",
            defaults={
                "type": "weather.current",
                "title": _current_title(current),
                "starts_at": _aware_weather_time(current.get("time")),
                "ends_at": None,
                "actionable": False,
                "payload": {
                    "provider": "Open-Meteo",
                    "temperature": current.get("temperature_2m"),
                    "apparent_temperature": current.get("apparent_temperature"),
                    "humidity": current.get("relative_humidity_2m"),
                    "weather_code": current.get("weather_code"),
                    "precipitation": current.get("precipitation"),
                    "wind_speed": current.get("wind_speed_10m"),
                    "latitude": data.get("latitude", lat),
                    "longitude": data.get("longitude", lon),
                },
            },
        )
        count += 1

    daily = data.get("daily") or {}
    active_daily_ids = []
    times = daily.get("time", [])
    for i, day in enumerate(times):
        external_id = f"weather:{day}"
        active_daily_ids.append(external_id)
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id=external_id,
            defaults={
                "type": "weather.forecast",
                "title": f"Wetter {day}",
                "starts_at": _aware_weather_time(day),
                "ends_at": None,
                "actionable": False,
                "payload": {
                    "provider": "Open-Meteo",
                    "weather_code": _at(daily.get("weather_code"), i),
                    "temp_max": _at(daily.get("temperature_2m_max"), i),
                    "temp_min": _at(daily.get("temperature_2m_min"), i),
                    "rain_probability": _at(daily.get("precipitation_probability_max"), i),
                    "wind_max": _at(daily.get("wind_speed_10m_max"), i),
                },
            },
        )
        count += 1
    FamilyEvent.objects.filter(source=source, type="weather.forecast").exclude(external_id__in=active_daily_ids).delete()
    return _finish(source, count)


def _aware_weather_time(value):
    if not value:
        return timezone.now()
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _at(values, index):
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]
