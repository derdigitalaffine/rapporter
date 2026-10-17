"""Minimal CalDAV scheduling facade for FamilyOS-internal participants.

FamilyOS does not deliver email invitations. Scheduling is limited to active
members of the authenticated family and maps to the FamilyEvent participant set.
The outbox acknowledges internal iTIP messages so native clients can expose
invitee editing without claiming external delivery.
"""
from uuid import UUID
from xml.etree import ElementTree as ET

from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from icalendar import Calendar

from . import calendar_subscription_dav as core
from .calendar_subscription_ics import MAX_BYTES, shared_events
from .calendar_subscription_participants import (
    ADDRESS_DOMAIN,
    UnknownFamilyAttendee,
    active_members,
    attendee_memberships,
    member_calendar_address,
    member_calendar_urn,
    member_label,
    member_principal_path,
    owner_member,
)
from .models import FamilyEvent

D = core.D
C = core.C
CS = core.CS


def _scheduled(result, allow=None):
    result['DAV'] = '1, calendar-access, calendar-schedule'
    if allow is not None:
        result['Allow'] = allow
    return result


def _unauthorized():
    result = core.response(status=401)
    result['WWW-Authenticate'] = 'Basic realm="FamilyOS calendar", charset="UTF-8"'
    return _scheduled(result)


def _authenticate(request):
    blocked = core.limited(request, request.META.get('REMOTE_ADDR', 'unknown'))
    if blocked:
        return None, _scheduled(blocked)
    grant = core.authenticate(request)
    if grant is None:
        return None, _unauthorized()
    return grant, None


def _href_property(name, href):
    value = core.element(C, name)
    value.append(core.element(D, 'href', href))
    return value


def _principal_propfind(request, grant, path):
    principal = f'/caldav/{grant.pk}/principal/'
    if path != principal:
        return _scheduled(core.response(status=404))
    depth = request.headers.get('Depth', 'infinity')
    if depth not in ('0', '1'):
        return _scheduled(core.response(status=403))
    try:
        root = core.xml_body(request) if request.body else core.element(D, 'propfind')
    except (ValueError, TypeError, ET.ParseError, OverflowError):
        return _scheduled(core.response(status=400))
    if root.tag != core.q(D, 'propfind') or root.find(core.q(D, 'propname')) is not None:
        return _scheduled(core.response(status=400))
    prop = root.find(core.q(D, 'prop'))
    requested = [node.tag for node in prop] if prop is not None else None

    home = f'/caldav/{grant.pk}/home/'
    principals = f'/caldav/{grant.pk}/principals/'
    values = core.props_for(grant, principal, 'principal')
    if requested is not None:
        if core.q(C, 'schedule-inbox-URL') in requested:
            values[core.q(C, 'schedule-inbox-URL')] = _href_property('schedule-inbox-URL', home + 'inbox/')
        if core.q(C, 'schedule-outbox-URL') in requested:
            values[core.q(C, 'schedule-outbox-URL')] = _href_property('schedule-outbox-URL', home + 'outbox/')
    rows = [(principal, values)]
    if depth == '1':
        rows.append((home, core.props_for(grant, home, 'home')))
        rows.append((principals, core.props_for(grant, principals, 'principal-collection')))
    return _scheduled(core.multistatus(rows, requested))


def _schedule_collection_values(grant, path, kind):
    values = core.props_for(grant, path, 'home')
    resource = values[core.q(D, 'resourcetype')]
    resource.append(core.element(C, f'schedule-{kind}'))

    components = core.element(C, 'supported-calendar-component-set')
    ET.SubElement(components, core.q(C, 'comp'), {'name': 'VEVENT'})
    values[core.q(C, 'supported-calendar-component-set')] = components

    formats = core.element(C, 'supported-calendar-data')
    ET.SubElement(formats, core.q(C, 'calendar-data'), {'content-type': 'text/calendar', 'version': '2.0'})
    values[core.q(C, 'supported-calendar-data')] = formats

    privileges = values[core.q(D, 'current-user-privilege-set')]
    privilege = ET.SubElement(privileges, core.q(D, 'privilege'))
    privilege.append(core.element(C, 'schedule-send' if kind == 'outbox' else 'schedule-deliver'))

    if kind == 'inbox':
        calendar = f'/caldav/{grant.pk}/home/family/'
        values[core.q(C, 'schedule-default-calendar-URL')] = _href_property('schedule-default-calendar-URL', calendar)
    return values


def _schedule_propfind(request, grant, path, kind):
    depth = request.headers.get('Depth', 'infinity')
    if depth not in ('0', '1'):
        return _scheduled(core.response(status=403))
    try:
        root = core.xml_body(request) if request.body else core.element(D, 'propfind')
    except (ValueError, TypeError, ET.ParseError, OverflowError):
        return _scheduled(core.response(status=400))
    if root.tag != core.q(D, 'propfind') or root.find(core.q(D, 'propname')) is not None:
        return _scheduled(core.response(status=400))
    prop = root.find(core.q(D, 'prop'))
    requested = [node.tag for node in prop] if prop is not None else None
    return _scheduled(core.multistatus([(path, _schedule_collection_values(grant, path, kind))], requested))


def _component_values(component, name):
    value = component.get(name)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _outbox_post(request, grant):
    if len(request.body) > MAX_BYTES or not request.body or b'\x00' in request.body or b'<!' in request.body:
        return _scheduled(core.response(status=400))
    content_type = request.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
    if content_type != 'text/calendar':
        return _scheduled(core.response(status=415))
    try:
        calendar = Calendar.from_ical(request.body)
        method = str(calendar.get('METHOD') or '').upper()
        if method not in ('REQUEST', 'CANCEL', 'REPLY'):
            raise ValueError()
        components = [item for item in calendar.subcomponents if item.name in ('VEVENT', 'VFREEBUSY')]
        if len(components) != 1:
            raise ValueError()
        component = components[0]
        attendee_memberships(grant, component)
        if component.get('ORGANIZER') is None:
            raise UnknownFamilyAttendee('organizer')
        recipients = _component_values(component, 'ATTENDEE')
    except UnknownFamilyAttendee:
        return _scheduled(core.response(status=403))
    except (ValueError, TypeError, KeyError):
        return _scheduled(core.response(status=400))

    root = core.element(C, 'schedule-response')
    for recipient in recipients:
        row = ET.SubElement(root, core.q(C, 'response'))
        target = ET.SubElement(row, core.q(C, 'recipient'))
        ET.SubElement(target, core.q(D, 'href')).text = str(recipient)
        ET.SubElement(row, core.q(C, 'request-status')).text = '2.0;Success'
    return _scheduled(core.response(ET.tostring(root, encoding='utf-8', xml_declaration=True)))


def _schedule_collection(request, grant, path, kind):
    allow = 'OPTIONS, PROPFIND, POST' if kind == 'outbox' else 'OPTIONS, PROPFIND'
    if request.method == 'OPTIONS':
        return _scheduled(core.response(), allow)
    if request.method == 'PROPFIND':
        return _scheduled(_schedule_propfind(request, grant, path, kind), allow)
    if request.method == 'POST' and kind == 'outbox':
        return _scheduled(_outbox_post(request, grant), allow)
    return _scheduled(core.response(status=405), allow)


def _member_email(member):
    return f'{member.pk}@{ADDRESS_DOMAIN}'


def _member_search_value(grant, member, tag):
    if tag == core.q(D, 'displayname'):
        return member_label(member)
    if tag == core.q(C, 'calendar-user-address-set'):
        return ' '.join((member_calendar_address(member), member_calendar_urn(member), member_principal_path(grant, member)))
    if tag == core.q(C, 'calendar-user-type'):
        return 'INDIVIDUAL'
    if tag == core.q(CS, 'email-address-set'):
        return _member_email(member)
    if tag == core.q(CS, 'first-name'):
        return (member.user.first_name or member_label(member).split(' ', 1)[0]).strip()
    if tag == core.q(CS, 'last-name'):
        return (member.user.last_name or '').strip()
    if tag == core.q(CS, 'record-type'):
        return 'users'
    raise ValueError()


def _member_search_props(grant, member):
    path = member_principal_path(grant, member)
    values = core.props_for(grant, path, 'member-principal', member=member)
    email_set = core.element(CS, 'email-address-set')
    email_set.append(core.element(CS, 'email-address', _member_email(member)))
    values[core.q(CS, 'email-address-set')] = email_set
    values[core.q(CS, 'first-name')] = core.element(CS, 'first-name', _member_search_value(grant, member, core.q(CS, 'first-name')))
    values[core.q(CS, 'last-name')] = core.element(CS, 'last-name', _member_search_value(grant, member, core.q(CS, 'last-name')))
    values[core.q(CS, 'record-type')] = core.element(CS, 'record-type', 'users')
    return values


def _matches(value, needle, match_type, caseless):
    if caseless:
        value = value.casefold(); needle = needle.casefold()
    if match_type == 'starts-with':
        return value.startswith(needle)
    if match_type == 'ends-with':
        return value.endswith(needle)
    if match_type == 'equals':
        return value == needle
    return needle in value


def _principal_property_search(root, grant):
    if root.tag != core.q(D, 'principal-property-search') or set(root.attrib) - {'test', 'type'}:
        raise ValueError()
    mode = root.get('test', 'allof')
    if mode not in ('allof', 'anyof'):
        raise ValueError()
    requested_type = root.get('type')
    if requested_type not in (None, '', 'INDIVIDUAL'):
        return core.multistatus([], [])

    searchable = {
        core.q(D, 'displayname'),
        core.q(C, 'calendar-user-address-set'),
        core.q(C, 'calendar-user-type'),
        core.q(CS, 'email-address-set'),
        core.q(CS, 'first-name'),
        core.q(CS, 'last-name'),
        core.q(CS, 'record-type'),
    }
    searches = root.findall(core.q(D, 'property-search'))
    if not searches or len(searches) > 8:
        raise ValueError()
    criteria = []
    for search in searches:
        if search.attrib:
            raise ValueError()
        prop = search.find(core.q(D, 'prop')); match = search.find(core.q(D, 'match'))
        if prop is None or match is None or len(prop) != 1 or prop[0].tag not in searchable:
            raise ValueError()
        if set(match.attrib) - {'caseless', 'match-type'}:
            raise ValueError()
        caseless_value = match.get('caseless', 'yes').lower()
        if caseless_value not in ('yes', 'no'):
            raise ValueError()
        match_type = match.get('match-type', 'contains')
        if match_type not in ('contains', 'starts-with', 'ends-with', 'equals'):
            raise ValueError()
        criteria.append((prop[0].tag, match.text or '', match_type, caseless_value != 'no'))

    requested_node = root.find(core.q(D, 'prop'))
    requested = [node.tag for node in requested_node] if requested_node is not None else list(searchable)
    allowed_requested = searchable | {core.q(D, 'resourcetype'), core.q(D, 'principal-URL')}
    if any(tag not in allowed_requested for tag in requested):
        raise ValueError()

    rows = []
    for member in active_members(grant):
        checks = [
            _matches(_member_search_value(grant, member, tag), needle, match_type, caseless)
            for tag, needle, match_type, caseless in criteria
        ]
        if (any(checks) if mode == 'anyof' else all(checks)):
            rows.append((member_principal_path(grant, member), _member_search_props(grant, member)))
        if len(rows) >= 100:
            break
    return core.multistatus(rows, requested)


def _principal_search_property_set():
    root = core.element(D, 'principal-search-property-set')
    for namespace, name, description in (
        (D, 'displayname', 'Display Name'),
        (CS, 'email-address-set', 'Email Addresses'),
        (CS, 'first-name', 'First Name'),
        (CS, 'last-name', 'Last Name'),
        (C, 'calendar-user-type', 'Calendar User Type'),
        (C, 'calendar-user-address-set', 'Calendar User Address Set'),
    ):
        item = ET.SubElement(root, core.q(D, 'principal-search-property'))
        prop = ET.SubElement(item, core.q(D, 'prop')); prop.append(core.element(namespace, name))
        ET.SubElement(item, core.q(D, 'description'), {'{http://www.w3.org/XML/1998/namespace}lang': 'en'}).text = description
    return core.response(ET.tostring(root, encoding='utf-8', xml_declaration=True))


def _event_id(grant, actual):
    prefix = f'/caldav/{grant.pk}/home/family/'
    if not actual.startswith(prefix) or not actual.endswith('.ics'):
        return None
    try:
        return UUID(actual[len(prefix):-4])
    except ValueError:
        return None


def _owner_can_write(grant, event):
    owner = owner_member(grant)
    return owner is not None and event.participants.filter(pk=owner.pk).exists()


def _put_event(request, grant, event_id, existing):
    current = core.event_etag(grant, existing) if existing is not None else None
    if request.META.get('HTTP_IF_NONE_MATCH') == '*' and existing is not None:
        return core.response(status=412)
    if request.META.get('HTTP_IF_MATCH') and request.META.get('HTTP_IF_MATCH') != current:
        return core.response(status=412)
    if existing is not None and not _owner_can_write(grant, existing):
        return core.response(status=403)
    try:
        title, starts_at, ends_at, payload, participants = core._parse_put(grant, existing, request.body)
    except UnknownFamilyAttendee:
        return core.response(status=409)
    except NotImplementedError:
        return core.response(status=409)
    except (ValueError, TypeError, KeyError):
        return core.response(status=400)

    with transaction.atomic():
        locked = FamilyEvent.objects.select_for_update().filter(pk=event_id, family=grant.family).first()
        if existing is None and locked is not None:
            return core.response(status=412)
        if existing is not None and (locked is None or core.event_etag(grant, locked) != current):
            return core.response(status=412)
        if locked is not None and (locked.source_id or locked.external_id or locked.type != 'calendar.event'):
            return core.response(status=403)
        if locked is not None and not _owner_can_write(grant, locked):
            return core.response(status=403)
        if locked is None:
            event = FamilyEvent(
                id=event_id,
                family=grant.family,
                type='calendar.event',
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                actionable=False,
                payload=payload,
                is_family_event=False,
            )
            event.save(force_insert=True)
            status = 201
        else:
            event = locked
            event.title = title
            event.starts_at = starts_at
            event.ends_at = ends_at
            event.payload = payload
            event.save(update_fields=['title', 'starts_at', 'ends_at', 'payload', 'updated_at'])
            status = 204
        event.participants.set(participants)
    result = core.response(status=status, content_type='text/calendar; charset=utf-8')
    result['ETag'] = core.event_etag(grant, event)
    return result


def _delete_event(request, grant, existing):
    if existing is None:
        return core.response(status=404)
    if not _owner_can_write(grant, existing):
        return core.response(status=403)
    current = core.event_etag(grant, existing)
    if request.META.get('HTTP_IF_MATCH') and request.META.get('HTTP_IF_MATCH') != current:
        return core.response(status=412)
    with transaction.atomic():
        locked = FamilyEvent.objects.select_for_update().filter(pk=existing.pk, family=grant.family).first()
        if locked is None:
            return core.response(status=404)
        if core.event_etag(grant, locked) != current:
            return core.response(status=412)
        if locked.source_id or locked.external_id or locked.type != 'calendar.event' or not _owner_can_write(grant, locked):
            return core.response(status=403)
        locked.delete()
    return core.response(status=204)


def _apply_schedule_tag(request, result):
    etag = result.get('ETag')
    if etag:
        result['Schedule-Tag'] = etag
    if result.status_code != 207 or b'schedule-tag' not in request.body or not result.content:
        return result
    try:
        root = ET.fromstring(result.content)
    except ET.ParseError:
        return result
    changed = False
    for row in root.findall(core.q(D, 'response')):
        found_prop = None
        etag_text = None
        missing = []
        for propstat in list(row.findall(core.q(D, 'propstat'))):
            status = propstat.find(core.q(D, 'status'))
            prop = propstat.find(core.q(D, 'prop'))
            if status is None or prop is None:
                continue
            status_text = status.text or ''
            if ' 200 ' in status_text:
                found_prop = prop
                etag_node = prop.find(core.q(D, 'getetag'))
                if etag_node is not None and etag_node.text:
                    etag_text = etag_node.text
            elif ' 404 ' in status_text:
                tag = prop.find(core.q(C, 'schedule-tag'))
                if tag is not None:
                    missing.append((propstat, prop, tag))
        if not etag_text or not missing:
            continue
        if found_prop is None:
            propstat = ET.SubElement(row, core.q(D, 'propstat'))
            found_prop = ET.SubElement(propstat, core.q(D, 'prop'))
            ET.SubElement(propstat, core.q(D, 'status')).text = 'HTTP/1.1 200 OK'
        ET.SubElement(found_prop, core.q(C, 'schedule-tag')).text = etag_text
        for propstat, prop, tag in missing:
            prop.remove(tag)
            if len(prop) == 0:
                row.remove(propstat)
        changed = True
    if changed:
        result.content = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return result


@csrf_exempt
def dav(request, path=''):
    actual = '/caldav/' + path
    schedule_match = request.META.get('HTTP_IF_SCHEDULE_TAG_MATCH')
    if schedule_match and not request.META.get('HTTP_IF_MATCH'):
        request.META['HTTP_IF_MATCH'] = schedule_match

    is_principal_propfind = request.method == 'PROPFIND' and actual.endswith('/principal/')
    is_schedule_collection = actual.endswith('/inbox/') or actual.endswith('/outbox/')

    if is_principal_propfind or is_schedule_collection:
        grant, error = _authenticate(request)
        if error is not None:
            return error
        home = f'/caldav/{grant.pk}/home/'
        inbox = home + 'inbox/'
        outbox = home + 'outbox/'
        if actual == inbox:
            return _schedule_collection(request, grant, inbox, 'inbox')
        if actual == outbox:
            return _schedule_collection(request, grant, outbox, 'outbox')
        if is_principal_propfind:
            return _principal_propfind(request, grant, actual)
        return _scheduled(core.response(status=404))

    if request.method == 'REPORT' and request.body:
        try:
            root = core.xml_body(request)
        except (ValueError, TypeError, ET.ParseError, OverflowError):
            root = None
        if root is not None and root.tag in (core.q(D, 'principal-property-search'), core.q(D, 'principal-search-property-set')):
            grant, error = _authenticate(request)
            if error is not None:
                return error
            principal = f'/caldav/{grant.pk}/principal/'
            principals = f'/caldav/{grant.pk}/principals/'
            if actual not in ('/caldav/', principal, principals):
                return _scheduled(core.response(status=403))
            try:
                result = _principal_property_search(root, grant) if root.tag == core.q(D, 'principal-property-search') else _principal_search_property_set()
            except (ValueError, TypeError):
                result = core.response(status=400)
            return _scheduled(result)

    if request.method in ('PUT', 'DELETE'):
        grant, error = _authenticate(request)
        if error is not None:
            return error
        event_id = _event_id(grant, actual)
        if event_id is None:
            return _scheduled(core.response(status=403))
        try:
            existing = next((event for event in shared_events(grant) if event.pk == event_id), None)
            result = _put_event(request, grant, event_id, existing) if request.method == 'PUT' else _delete_event(request, grant, existing)
        except core.CalendarCapacityError:
            result = core.response(status=507)
        return _apply_schedule_tag(request, _scheduled(result))

    return _apply_schedule_tag(request, _scheduled(core.dav(request, path)))
