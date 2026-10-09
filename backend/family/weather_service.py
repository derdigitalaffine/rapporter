from datetime import timedelta
from django.utils import timezone

from .models import FamilyEvent, IntegrationSource


def _forecast_date(event):
    if event.external_id.startswith("weather:"):
        value=event.external_id.removeprefix("weather:")
        if value and value!="current": return value
    return event.starts_at.date().isoformat() if event.starts_at else None


def weather_payload(family):
    source=IntegrationSource.objects.filter(family=family,kind="weather",enabled=True).order_by("-last_success_at","-updated_at").first()
    current=FamilyEvent.objects.filter(family=family,type="weather.current").order_by("-starts_at","-updated_at").first()
    forecasts=list(FamilyEvent.objects.filter(family=family,type="weather.forecast").order_by("starts_at","external_id")[:7])
    now=timezone.now()
    alerts=FamilyEvent.objects.filter(family=family,type="weather.warning").filter(ends_at__isnull=True)|FamilyEvent.objects.filter(family=family,type="weather.warning",ends_at__gte=now)
    alerts=alerts.distinct().order_by("starts_at")[:8]
    last_success=getattr(source,"last_success_at",None) or getattr(source,"last_synced_at",None)
    stale=bool(source and (source.last_sync_status=="error" or not last_success or last_success<now-timedelta(hours=6)))
    current_payload=dict(current.payload or {}) if current else None
    days=[]
    for event in forecasts:
        payload=event.payload or {}
        days.append({
            "date":_forecast_date(event),"weather_code":payload.get("weather_code"),
            "temp_min":payload.get("temp_min"),"temp_max":payload.get("temp_max"),
            "apparent_temp_min":payload.get("apparent_temp_min"),"apparent_temp_max":payload.get("apparent_temp_max"),
            "precipitation_probability":payload.get("rain_probability"),"precipitation_sum":payload.get("precipitation_sum"),
            "wind_max":payload.get("wind_max"),"wind_gust_max":payload.get("wind_gust_max"),
            "sunrise":payload.get("sunrise"),"sunset":payload.get("sunset"),"uv_index_max":payload.get("uv_index_max"),
        })
    location={"latitude":None,"longitude":None,"label":""}
    if source:
        config=source.config or {};location={"latitude":config.get("latitude"),"longitude":config.get("longitude"),"label":config.get("location") or config.get("label") or ""}
    if current_payload:
        location["latitude"]=current_payload.get("latitude",location["latitude"]);location["longitude"]=current_payload.get("longitude",location["longitude"])
    return {
        "source":{"provider":"Open-Meteo","last_success_at":last_success,"stale":stale,"location":location,"status":getattr(source,"last_sync_status","never") if source else "missing"},
        "current":({"observed_at":current.starts_at,"temperature":current_payload.get("temperature"),"apparent_temperature":current_payload.get("apparent_temperature"),"weather_code":current_payload.get("weather_code"),"humidity":current_payload.get("humidity"),"precipitation":current_payload.get("precipitation"),"wind_speed":current_payload.get("wind_speed")} if current and current_payload else None),
        "days":days,
        "alerts":[{"id":str(event.id),"title":event.title,"starts_at":event.starts_at,"ends_at":event.ends_at,"region":event.payload.get("region"),"level":event.payload.get("level"),"description":event.payload.get("description"),"instruction":event.payload.get("instruction"),"provider":event.payload.get("provider","DWD")} for event in alerts],
    }
