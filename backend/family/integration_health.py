from datetime import timedelta

from django.utils import timezone

from .extended_integrations import sync_source as raw_sync_source
from .weather_integrations import sync_dwd, sync_weather


def _sync_source(source):
    adapter = (source.config or {}).get("adapter")
    if adapter == "rlp_school_holidays":
        from .school_holidays import sync_school_holidays
        return sync_school_holidays(source)
    if adapter == "dwd":
        return sync_dwd(source)
    if adapter == "weather":
        return sync_weather(source)
    if adapter == "caldav":
        from .caldav_models import CalDavConnection
        from .caldav_sync import sync_connection
        connection_id = (source.config or {}).get("caldav_connection")
        connection = CalDavConnection.objects.filter(id=connection_id, family=source.family, enabled=True).first()
        if not connection:
            raise ValueError("caldav_connection_missing")
        result = sync_connection(connection)
        return result["pulled"] + result["remote_updates"] + result["pushed"] + result["deleted"]
    return raw_sync_source(source)


def sync_with_health(source, *, force=False):
    now = timezone.now()
    if not source.enabled:
        return 0
    if not force and source.next_sync_at and source.next_sync_at > now:
        return 0

    source.last_attempt_at = now
    source.last_sync_status = "running"
    source.save(update_fields=["last_attempt_at", "last_sync_status", "updated_at"])
    try:
        count = _sync_source(source)
    except Exception as exc:
        source.refresh_from_db()
        failures = source.consecutive_failures + 1
        delay_minutes = min(360, 5 * (2 ** min(failures - 1, 7)))
        source.last_attempt_at = now
        source.last_sync_status = "error"
        source.last_sync_error = str(exc)[:4000]
        source.consecutive_failures = failures
        source.next_sync_at = now + timedelta(minutes=delay_minutes)
        source.save(update_fields=[
            "last_attempt_at", "last_sync_status", "last_sync_error",
            "consecutive_failures", "next_sync_at", "updated_at",
        ])
        raise

    source.refresh_from_db()
    source.last_attempt_at = now
    source.last_success_at = timezone.now()
    source.last_sync_status = "success"
    source.last_sync_error = ""
    source.consecutive_failures = 0
    adapter = (source.config or {}).get("adapter")
    if adapter == "rlp_school_holidays":
        source.next_sync_at = timezone.now() + timedelta(days=1)
    elif adapter == "caldav":
        source.next_sync_at = timezone.now() + timedelta(minutes=15)
    else:
        source.next_sync_at = None
    source.save(update_fields=[
        "last_attempt_at", "last_success_at", "last_sync_status",
        "last_sync_error", "consecutive_failures", "next_sync_at", "updated_at",
    ])
    return count
