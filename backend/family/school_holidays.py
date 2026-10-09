"""Read-only state holiday calendar, fetched exclusively from the RLP ministry."""
import re
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .integrations import _finish, _get, validate_ics_bytes
from .models import FamilyEvent, IntegrationSource

OFFICIAL_PAGE = "https://bm.rlp.de/service/ferientermine"
PROVIDER = "Ministerium für Bildung Rheinland-Pfalz"
SCHOOL_NOTE = "Bewegliche Ferientage legt jede Schule selbst fest; sie sind hier nicht enthalten."
HOLIDAYS = r"(Sommer|Herbst|Weihnachts|Winter|Oster|Pfingst)ferien"


class CalendarLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href", "")
            url = urljoin(OFFICIAL_PAGE, href)
            parsed = urlparse(url)
            if parsed.scheme == "https" and parsed.hostname == "bm.rlp.de" and parsed.path.lower().endswith(".ics"):
                self.links.append(url)


def sync_school_holidays(source):
    # User-provided endpoint/config cannot redirect this curated integration elsewhere.
    page = _get(OFFICIAL_PAGE)
    parser = CalendarLinks()
    parser.feed(page.text)
    links = sorted(set(parser.links))
    if len(links) != 1:
        raise ValueError("Der amtliche RLP-Ferienkalender wurde nicht eindeutig gefunden. Bestehende Termine bleiben erhalten.")
    calendar = validate_ics_bytes(_get(links[0]).content)
    rows = {}
    for event in calendar.walk("VEVENT"):
        title = str(event.get("summary", ""))
        match = re.search(HOLIDAYS + r".*?(\d{4})/(\d{4})", title)
        start, end = event.decoded("dtstart", None), event.decoded("dtend", None)
        if not match or not isinstance(start, date) or isinstance(start, datetime) or not isinstance(end, date) or isinstance(end, datetime):
            raise ValueError("Der amtliche Ferienkalender enthält einen unerwarteten Termin.")
        if int(match[3]) != int(match[2]) + 1 or not 0 < (end - start).days <= 90:
            raise ValueError("Der amtliche Ferienkalender enthält ungültige Datumsbereiche.")
        external_id = f"rlp-holiday:{match[1].lower()}:{match[2]}-{match[3]}"
        if external_id in rows:
            raise ValueError("Der amtliche Ferienkalender enthält doppelte Ferienblöcke.")
        rows[external_id] = (title, start, end)
    today = timezone.now().astimezone(ZoneInfo("Europe/Berlin")).date()
    if not rows or not any(end > today for _, _, end in rows.values()):
        raise ValueError("Der amtliche Ferienkalender enthält keine aktuellen oder künftigen Ferien. Bestehende Termine bleiben erhalten.")
    # School dates are geographic civil dates, regardless of the family/device timezone.
    zone = ZoneInfo("Europe/Berlin")
    with transaction.atomic():
        IntegrationSource.objects.select_for_update().get(pk=source.pk)
        for external_id, (title, start, end) in rows.items():
            FamilyEvent.objects.update_or_create(
                family=source.family, source=source, external_id=external_id,
                defaults={"type": "school.holiday", "title": title[:200],
                          "starts_at": datetime.combine(start, time.min, zone),
                          "ends_at": datetime.combine(end, time.min, zone), "actionable": False,
                          "payload": {"provider": PROVIDER, "source_url": OFFICIAL_PAGE,
                                      "all_day": True, "timezone": "Europe/Berlin",
                                      "date_start": start.isoformat(), "date_end_exclusive": end.isoformat(),
                                      "description": SCHOOL_NOTE}},
            )
        # Removed/corrected blocks disappear only after the entire response was validated.
        FamilyEvent.objects.filter(source=source, type="school.holiday").exclude(external_id__in=rows).delete()
        return _finish(source, len(rows))
