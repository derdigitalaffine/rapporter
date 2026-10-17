"""FamilyOS CalDAV participant identities without external invitation delivery.

Membership UUIDs are the canonical identity. A reserved `.invalid` mailto form is
also exposed because calendar clients commonly expect a mail-shaped calendar user
address. No mailbox exists and FamilyOS never sends external scheduling messages
for these addresses.
"""
from urllib.parse import urlsplit
from uuid import UUID

from django.db.models import prefetch_related_objects
from icalendar import Calendar, vCalAddress

from .calendar_subscription_ics import CalendarCapacityError, MAX_BYTES, calendar_bytes
from .models import Membership

ADDRESS_DOMAIN = 'members.familyos.invalid'


class UnknownFamilyAttendee(ValueError):
    pass


def member_label(member):
    return (member.display_name or member.user.get_full_name() or member.user.get_username()).strip() or 'Family member'


def member_calendar_address(member):
    return f'mailto:{member.pk}@{ADDRESS_DOMAIN}'


def member_calendar_urn(member):
    return f'urn:uuid:{member.pk}'


def member_principal_path(grant, member):
    return f'/caldav/{grant.pk}/principals/{member.pk}/'


def active_members(grant):
    return list(
        Membership.objects.filter(family_id=grant.family_id, user__is_active=True)
        .select_related('user')
        .order_by('created_at', 'id')
    )


def owner_member(grant, members=None):
    rows = members if members is not None else active_members(grant)
    return next((member for member in rows if member.user_id == grant.created_by_id), None)


def _event_uid(event):
    payload = event.payload if isinstance(event.payload, dict) else {}
    value = payload.get('caldav_uid')
    return value.strip()[:255] if isinstance(value, str) and value.strip() else f'{event.pk}@familyos'


def calendar_bytes_with_participants(grant, events, detail_level='full'):
    events = list(events)
    data = calendar_bytes(grant.family, events, detail_level)
    if not events:
        return data
    prefetch_related_objects(events, 'participants__user')
    by_uid = {_event_uid(event): event for event in events}
    members = active_members(grant)
    owner = owner_member(grant, members)
    calendar = Calendar.from_ical(data)
    for component in calendar.walk('VEVENT'):
        event = by_uid.get(str(component.get('UID') or ''))
        if event is None:
            continue
        participants = [member for member in event.participants.all() if member.user.is_active]
        if owner is not None and any(member.pk == owner.pk for member in participants):
            organizer = vCalAddress(member_calendar_address(owner))
            organizer.params['CN'] = member_label(owner)
            organizer.params['CUTYPE'] = 'INDIVIDUAL'
            organizer.params['SCHEDULE-AGENT'] = 'CLIENT'
            component.add('ORGANIZER', organizer, encode=0)
        for member in participants:
            attendee = vCalAddress(member_calendar_address(member))
            attendee.params['CN'] = member_label(member)
            attendee.params['CUTYPE'] = 'INDIVIDUAL'
            attendee.params['ROLE'] = 'REQ-PARTICIPANT'
            attendee.params['SCHEDULE-AGENT'] = 'CLIENT'
            component.add('ATTENDEE', attendee, encode=0)
    data = calendar.to_ical()
    if len(data) > MAX_BYTES:
        raise CalendarCapacityError()
    return data


def _values(component, name):
    value = component.get(name)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _membership_id_from_address(grant, value):
    raw = str(value or '').strip()
    lowered = raw.lower()
    if lowered.startswith('mailto:') and lowered.endswith('@' + ADDRESS_DOMAIN):
        token = raw[7:-(len(ADDRESS_DOMAIN) + 1)]
        return UUID(token)
    if lowered.startswith('urn:uuid:'):
        return UUID(raw[9:])
    parsed = urlsplit(raw)
    path = parsed.path if parsed.scheme or parsed.netloc else raw
    prefix = f'/caldav/{grant.pk}/principals/'
    if path.startswith(prefix) and path.endswith('/'):
        return UUID(path[len(prefix):-1])
    raise UnknownFamilyAttendee(raw)


def attendee_memberships(grant, component):
    members = {member.pk: member for member in active_members(grant)}
    owner = owner_member(grant, list(members.values()))
    if owner is None:
        raise UnknownFamilyAttendee('calendar owner')

    organizers = _values(component, 'ORGANIZER')
    if len(organizers) > 1:
        raise UnknownFamilyAttendee('multiple organizers')
    if organizers:
        try:
            organizer_id = _membership_id_from_address(grant, organizers[0])
        except (ValueError, TypeError) as exc:
            raise UnknownFamilyAttendee(str(organizers[0] or '')) from exc
        if organizer_id != owner.pk:
            raise UnknownFamilyAttendee(str(organizers[0] or ''))

    selected = [owner]
    seen = {owner.pk}
    for value in _values(component, 'ATTENDEE'):
        try:
            membership_id = _membership_id_from_address(grant, value)
        except (ValueError, TypeError) as exc:
            raise UnknownFamilyAttendee(str(value or '')) from exc
        member = members.get(membership_id)
        if member is None:
            raise UnknownFamilyAttendee(str(value or ''))
        if member.pk not in seen:
            selected.append(member)
            seen.add(member.pk)
    return selected
