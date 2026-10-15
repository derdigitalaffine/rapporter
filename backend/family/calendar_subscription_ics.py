"""Read-only projection of explicit shared native FamilyEvents (no participants/payload dumps)."""
from functools import lru_cache
from datetime import date, datetime, timedelta, timezone as dt_timezone
from icalendar import Calendar, Event, Timezone
from django.utils import timezone
from .models import FamilyEvent
from .action_schedule import _days, local_datetime
from .calendar_recurrence import family_zone, recurrence_dict, project_event

MAX_RESOURCES = 2000
MAX_BYTES = 8 * 1024 * 1024
WEEKDAYS = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']


class CalendarCapacityError(Exception):
    pass


def shared_events(grant):
    # The whole-family flag is canonical and independent of attendance selection.
    # Selected-only/personal events, imports, health and virtual rows stay excluded.
    rows = list(FamilyEvent.objects.filter(family_id=grant.family_id, source__isnull=True,
        type='calendar.event', is_family_event=True, external_id='', starts_at__isnull=False).select_related('family').order_by('id')[:MAX_RESOURCES + 1])
    if len(rows) > MAX_RESOURCES:
        raise CalendarCapacityError()
    return rows


def projection(event, start, end):
    base = {'starts_at': event.starts_at.isoformat(), 'ends_at': event.ends_at.isoformat() if event.ends_at else None,
            'payload': event.payload if isinstance(event.payload, dict) else {}}
    rows = {}
    while start <= end:
        stop = min(end, start + timedelta(days=89))
        for row in project_event(event, base, start, stop):
            rows[row['starts_at']] = row
        start = stop + timedelta(days=1)
    return list(rows.values())


def overlaps(event, start, end):
    payload = event.payload if isinstance(event.payload, dict) else {}
    recurrence = recurrence_dict(payload.get('recurrence'))
    if not recurrence:
        return (end is None or event.starts_at < end) and (start is None or (event.ends_at or event.starts_at + timedelta(seconds=1)) > start)
    # Native rules have no UNTIL/COUNT. An open-ended future query intersects
    # every valid recurring series without expanding an unbounded timeline.
    if end is None:
        return True
    zone = family_zone(event.family)
    anchor = event.starts_at.astimezone(zone)
    wall_span = ((event.ends_at.astimezone(zone).replace(tzinfo=None) - anchor.replace(tzinfo=None))
                 if event.ends_at else timedelta(seconds=1))
    if wall_span > timedelta(days=1830):
        raise CalendarCapacityError()
    after = anchor.date() if start is None else max(anchor.date(), (start - max(timedelta(0), wall_span)).astimezone(zone).date() - timedelta(days=1))
    schedule = {'anchor_date': anchor.date().isoformat(), 'recurrence': recurrence}
    for day in _days(schedule, after):
        occurrence = local_datetime(day, anchor.replace(tzinfo=None).time(), zone)
        if occurrence >= end:
            return False
        naive_end = datetime.combine(day, anchor.replace(tzinfo=None).time()) + wall_span
        occurrence_end = local_datetime(naive_end.date(), naive_end.time(), zone)
        if start is None or occurrence_end > start:
            return True
    return False


def event_component(event):
    zone = family_zone(event.family)
    payload = event.payload if isinstance(event.payload, dict) else {}
    component = Event()
    component.add('uid', f'{event.pk}@familyos')
    component.add('dtstamp', event.updated_at.astimezone(dt_timezone.utc))
    component.add('last-modified', event.updated_at.astimezone(dt_timezone.utc))
    component.add('summary', event.title)
    all_day = bool(payload.get('all_day'))
    start = event.starts_at.astimezone(zone)
    end = event.ends_at.astimezone(zone) if event.ends_at else None
    recurrence = recurrence_dict(payload.get('recurrence'))
    shift = timedelta(0)
    if recurrence:
        first = next(_days({'anchor_date': start.date().isoformat(), 'recurrence': recurrence}, start.date()), None)
        if first is None:
            raise CalendarCapacityError()
        shift = first - start.date()
        # Native projection may begin after the stored anchor (e.g. first Monday).
        # Retain the nominal wall clock for subsequent RFC recurrence instances.
        if shift:
            start = (start.replace(tzinfo=None) + shift).replace(tzinfo=zone)
            if end is not None:
                end = (end.replace(tzinfo=None) + shift).replace(tzinfo=zone)
    if all_day:
        try:
            day = date.fromisoformat(payload['date_start']) + shift if payload.get('date_start') else start.date()
            last = date.fromisoformat(payload['date_end_exclusive']) + shift if payload.get('date_end_exclusive') else day + timedelta(days=1)
        except (ValueError, TypeError):
            day, last = start.date(), start.date() + timedelta(days=1)
        component.add('dtstart', day); component.add('dtend', max(day + timedelta(days=1), last))
    else:
        component.add('dtstart', start)
        if end is not None:
            component.add('dtend', max(start + timedelta(seconds=1), end))
    # Deliberate export allow-list: no attendees, organizer, URLs, documents,
    # child/health references, notes or arbitrary payload fields.
    if recurrence:
        frequency = recurrence['frequency']
        if frequency == 'quarterly':
            # Canonical quarterly semantics include clamped dates/nth day of quarter,
            # which are not equivalent to MONTHLY;INTERVAL=3. Reuse core projection.
            today = timezone.localdate()
            rows = projection(event, today - timedelta(days=366), today + timedelta(days=1096))
            dates = []
            for row in rows:
                value = date.fromisoformat(row['payload']['date_start']) if all_day else datetime.fromisoformat(row['starts_at']).astimezone(zone)
                if value != (component.decoded('dtstart')):
                    dates.append(value)
            if dates:
                component.add('rdate', dates)
        else:
            rule = {'freq': frequency.upper(), 'interval': recurrence.get('interval', 1)}
            names = WEEKDAYS
            if recurrence.get('weekdays'):
                rule['byday'] = [WEEKDAYS[names.index(d)] for d in recurrence['weekdays']]
            if recurrence.get('nth_weekdays'):
                rule['byday'] = [f"{n['ordinal']}{WEEKDAYS[names.index(n['weekday'])]}" for n in recurrence['nth_weekdays']]
            if recurrence.get('month_days'):
                rule['bymonthday'] = recurrence['month_days']
            if recurrence.get('months'):
                rule['bymonth'] = recurrence['months']
            component.add('rrule', rule)
    return component


@lru_cache(maxsize=32)
def timezone_component(zone):
    return Timezone.from_tzinfo(zone, first_date=date(1970, 1, 1), last_date=date(2100, 1, 1))


def calendar_bytes(family, events):
    calendar = Calendar()
    calendar.add('prodid', '-//FamilyOS//Family Calendar//EN')
    calendar.add('version', '2.0')
    calendar.add('x-wr-calname', family.name)
    calendar.add('x-wr-timezone', str(family_zone(family)))
    events = list(events)
    if events:
        # Include transition rules so local recurring times retain DST in clients.
        calendar.add_component(timezone_component(family_zone(family)))
    for event in events:
        calendar.add_component(event_component(event))
    data = calendar.to_ical()
    if len(data) > MAX_BYTES:
        raise CalendarCapacityError()
    return data
