import ipaddress
import socket
from urllib.parse import urlparse
import requests
from icalendar import Calendar
from django.utils import timezone
from .models import FamilyEvent, IntegrationSource


def _safe_public_https(url: str):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only public HTTPS endpoints are allowed")
    for info in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Private network endpoints are not allowed")


def sync_ics(source: IntegrationSource):
    _safe_public_https(source.endpoint)
    response = requests.get(source.endpoint, timeout=12, headers={"User-Agent": "fam-uh-le/0.1"})
    response.raise_for_status()
    calendar = Calendar.from_ical(response.content)
    count = 0
    for component in calendar.walk("VEVENT"):
        uid = str(component.get("uid", ""))
        title = str(component.get("summary", "Termin"))
        start = component.decoded("dtstart", None)
        end = component.decoded("dtend", None)
        if start and not hasattr(start, "hour"):
            start = timezone.make_aware(timezone.datetime.combine(start, timezone.datetime.min.time()))
        if end and not hasattr(end, "hour"):
            end = timezone.make_aware(timezone.datetime.combine(end, timezone.datetime.min.time()))
        FamilyEvent.objects.update_or_create(
            family=source.family,
            source=source,
            external_id=uid or f"{title}:{start}",
            defaults={"type": source.config.get("event_type", "calendar.event"), "title": title, "starts_at": start, "ends_at": end, "payload": {"location": str(component.get("location", ""))}},
        )
        count += 1
    source.last_synced_at = timezone.now()
    source.save(update_fields=["last_synced_at", "updated_at"])
    return count


def sync_source(source: IntegrationSource):
    if source.kind in {IntegrationSource.Kind.ICS, IntegrationSource.Kind.WASTE} and source.endpoint:
        return sync_ics(source)
    return 0
