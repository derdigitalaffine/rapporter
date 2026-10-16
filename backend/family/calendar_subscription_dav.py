"""Bounded CalDAV endpoint for the FamilyOS family calendar.

The calendar is scoped by a revocable CalendarSubscription credential. Reads only
project native family-shared events; PUT and DELETE write those same resources
back to FamilyOS with HTTP conditional request protection. Family memberships are
exposed as searchable CalDAV principals and ATTENDEE values, but no scheduling
inbox/outbox or invitation delivery is implemented.
"""
import base64
import binascii
import hashlib
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from urllib.parse import urlsplit
from uuid import UUID
from xml.etree import ElementTree as ET

from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from icalendar import Calendar

from auth_abuse.service import enforce
from .calendar_recurrence import family_zone
from .calendar_subscription_service import resolve_token, origin
from .calendar_subscription_ics import shared_events, calendar_bytes, overlaps, CalendarCapacityError, MAX_BYTES
from .calendar_subscription_participants import (
    UnknownFamilyAttendee,
    active_members,
    attendee_memberships,
    calendar_bytes_with_participants,
    member_calendar_address,
    member_calendar_urn,
    member_label,
    member_principal_path,
)
from .calendar_subscription_views import private
from .models import FamilyEvent

D = 'DAV:'
C = 'urn:ietf:params:xml:ns:caldav'
CS = 'http://calendarserver.org/ns/'
CALDAV_DETAIL_LEVEL = 'full'
ET.register_namespace('d', D); ET.register_namespace('c', C); ET.register_namespace('cs', CS)


def q(namespace, name):
    return f'{{{namespace}}}{name}'


def element(namespace, name, text=None):
    result = ET.Element(q(namespace, name)); result.text = text
    return result


def response(data=b'', status=200, content_type='application/xml; charset=utf-8'):
    result = private(HttpResponse(data, status=status, content_type=content_type))
    result['DAV'] = '1, calendar-access'
    result['Allow'] = 'OPTIONS, PROPFIND, REPORT, GET, HEAD, PUT, DELETE'
    return result


def limited(request, identifier):
    decision = enforce('calendar.subscription.read', request=request, identifier=identifier)
    if decision.allowed:
        return None
    result = response(status=429); result['Retry-After'] = str(decision.retry_after)
    return result


def event_data(grant, event):
    return calendar_bytes_with_participants(grant, [event], CALDAV_DETAIL_LEVEL)


def event_etag(grant, event):
    return '"' + hashlib.sha256(event_data(grant, event)).hexdigest() + '"'


def ics_response(request, grant, events, detail_level=None, include_participants=False):
    data = (
        calendar_bytes_with_participants(grant, events, detail_level or grant.detail_level)
        if include_participants else calendar_bytes(grant.family, events, detail_level or grant.detail_level)
    )
    etag = '"' + hashlib.sha256(data).hexdigest() + '"'
    result = response(b'' if request.method == 'HEAD' else data, content_type='text/calendar; charset=utf-8')
    if request.headers.get('If-None-Match') in (etag, '*'):
        result = response(status=304, content_type='text/calendar; charset=utf-8')
    result['ETag'] = etag
    result['Content-Disposition'] = 'inline; filename="familyos.ics"'
    return result


@csrf_exempt
def feed(request, token):
    if request.method not in ('GET', 'HEAD'):
        return response(status=405)
    blocked = limited(request, token)
    if blocked:
        return blocked
    grant = resolve_token(token)
    if grant is None:
        return response(status=404)
    try:
        return ics_response(request, grant, shared_events(grant))
    except CalendarCapacityError:
        return response(status=507)


def authenticate(request):
    header = request.headers.get('Authorization', '')
    try:
        kind, value = header.split(' ', 1)
        if kind.lower() != 'basic' or len(value) > 1024:
            return None
        username, token = base64.b64decode(value, validate=True).decode('utf-8').split(':', 1)
    except (ValueError, UnicodeError, binascii.Error):
        return None
    return resolve_token(token, username)


def xml_body(request):
    if int(request.META.get('CONTENT_LENGTH') or 0) > 65536:
        raise ValueError()
    body = request.body
    if len(body) > 65536 or b'<!' in body or b'\x00' in body:
        raise ValueError()
    root = ET.fromstring(body)
    def bounded(node, depth=0):
        if depth > 12 or len(list(root.iter())) > 1000:
            raise ValueError()
        for child in node:
            bounded(child, depth + 1)
    bounded(root)
    return root


def _owner_member(grant):
    return next((member for member in active_members(grant) if member.user_id == grant.created_by_id), None)


def props_for(grant, path, kind, etag=None, data=None, member=None):
    principal = f'/caldav/{grant.pk}/principal/'
    principals = f'/caldav/{grant.pk}/principals/'
    home = f'/caldav/{grant.pk}/home/'
    values = {}
    def add(ns, name, text=None, child=None):
        value = element(ns, name, text)
        if child is not None:
            value.append(child)
        values[q(ns, name)] = value
        return value
    resource = add(D, 'resourcetype')
    if kind != 'event':
        resource.append(element(D, 'collection'))
    if kind in ('principal', 'member-principal'):
        resource.append(element(D, 'principal'))
    if kind == 'calendar':
        resource.append(element(C, 'calendar'))
    display = member_label(member) if member is not None else grant.family.name if kind == 'calendar' else 'FamilyOS'
    add(D, 'displayname', display)
    add(D, 'current-user-principal', child=element(D, 'href', principal))
    principal_url = member_principal_path(grant, member) if member is not None else principal
    add(D, 'principal-URL', child=element(D, 'href', principal_url))
    collection_set = add(D, 'principal-collection-set'); collection_set.append(element(D, 'href', principals))
    add(C, 'calendar-home-set', child=element(D, 'href', home))
    add(D, 'owner', child=element(D, 'href', principal))
    identity = member if member is not None else _owner_member(grant) if kind == 'principal' else None
    if identity is not None:
        addresses = add(C, 'calendar-user-address-set')
        for value in (member_calendar_address(identity), member_calendar_urn(identity), member_principal_path(grant, identity)):
            addresses.append(element(D, 'href', value))
        add(C, 'calendar-user-type', 'INDIVIDUAL')
    privileges = add(D, 'current-user-privilege-set')
    for name in (('read',) if kind not in ('calendar', 'event') else ('read', 'write')):
        privilege = ET.SubElement(privileges, q(D, 'privilege')); privilege.append(element(D, name))
    reports = add(D, 'supported-report-set')
    if kind == 'calendar':
        for name in ('calendar-query', 'calendar-multiget'):
            supported = ET.SubElement(reports, q(D, 'supported-report')); report = ET.SubElement(supported, q(D, 'report')); report.append(element(C, name))
        components = add(C, 'supported-calendar-component-set'); ET.SubElement(components, q(C, 'comp'), {'name': 'VEVENT'})
        formats = add(C, 'supported-calendar-data'); ET.SubElement(formats, q(C, 'calendar-data'), {'content-type': 'text/calendar', 'version': '2.0'})
        add(CS, 'getctag', etag)
        add(C, 'max-resource-size', str(MAX_BYTES))
    if kind in ('root', 'principal', 'principal-collection'):
        for name in ('principal-property-search', 'principal-search-property-set'):
            supported = ET.SubElement(reports, q(D, 'supported-report')); report = ET.SubElement(supported, q(D, 'report')); report.append(element(D, name))
    if etag:
        add(D, 'getetag', etag)
    if data is not None:
        add(D, 'getcontenttype', 'text/calendar; charset=utf-8')
        add(D, 'getcontentlength', str(len(data)))
        add(C, 'calendar-data', data.decode('utf-8'))
    return values


def multistatus(rows, requested):
    root = element(D, 'multistatus')
    for path, values in rows:
        row = ET.SubElement(root, q(D, 'response')); ET.SubElement(row, q(D, 'href')).text = path
        if values is None:
            ET.SubElement(row, q(D, 'status')).text = 'HTTP/1.1 404 Not Found'; continue
        names = requested if requested is not None else [key for key in values if key != q(C, 'calendar-data')]
        for found, status in ((True, '200 OK'), (False, '404 Not Found')):
            selected = [name for name in names if (name in values) == found]
            if not selected:
                continue
            propstat = ET.SubElement(row, q(D, 'propstat')); prop = ET.SubElement(propstat, q(D, 'prop'))
            for name in selected:
                prop.append(values[name] if found else ET.Element(name))
            ET.SubElement(propstat, q(D, 'status')).text = 'HTTP/1.1 ' + status
    data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    if len(data) > MAX_BYTES:
        raise CalendarCapacityError()
    return response(data, status=207)


def query_range(root):
    allowed = {q(C, 'filter'), q(C, 'comp-filter'), q(C, 'time-range')}
    filters = root.findall(q(C, 'filter'))
    for filters_root in filters:
        for node in filters_root.iter():
            attributes = {'name'} if node.tag == q(C, 'comp-filter') else {'start', 'end'} if node.tag == q(C, 'time-range') else set()
            if node.tag not in allowed or set(node.attrib) - attributes or (node.tag == q(C, 'comp-filter') and node.get('name') not in ('VCALENDAR', 'VEVENT')):
                raise ValueError()
    ranges = root.findall('.//' + q(C, 'time-range'))
    if len(ranges) > 1:
        raise ValueError()
    if not ranges:
        return None
    node = ranges[0]
    if not node.attrib or set(node.attrib) - {'start', 'end'}:
        raise ValueError()
    start, end = [datetime.strptime(node.get(key), '%Y%m%dT%H%M%SZ').replace(tzinfo=dt_timezone.utc) if node.get(key) else None for key in ('start', 'end')]
    if start is not None and end is not None and (end <= start or end - start > timedelta(days=1830)):
        raise ValueError()
    return start, end


def report_properties(prop):
    if prop is None:
        return [q(D, 'getetag'), q(C, 'calendar-data')]
    requested = []
    for node in prop:
        if node.tag != q(C, 'calendar-data'):
            if list(node) or node.attrib:
                raise ValueError()
            requested.append(node.tag)
            continue
        if node.attrib:
            raise ValueError()
        children = list(node)
        if len(children) > 1:
            raise ValueError()
        if children:
            expand = children[0]
            if expand.tag != q(C, 'expand') or list(expand) or set(expand.attrib) != {'start', 'end'}:
                raise ValueError()
            start, end = [
                datetime.strptime(expand.get(key), '%Y%m%dT%H%M%SZ').replace(tzinfo=dt_timezone.utc)
                for key in ('start', 'end')
            ]
            if end <= start or end - start > timedelta(days=1830):
                raise ValueError()
        requested.append(node.tag)
    return requested


def _principal_value(member, tag):
    if tag == q(D, 'displayname'):
        return member_label(member)
    if tag == q(C, 'calendar-user-address-set'):
        return ' '.join((member_calendar_address(member), member_calendar_urn(member)))
    if tag == q(C, 'calendar-user-type'):
        return 'INDIVIDUAL'
    raise ValueError()


def principal_property_search(root, grant):
    if root.tag != q(D, 'principal-property-search') or root.attrib:
        raise ValueError()
    searches = root.findall(q(D, 'property-search'))
    if not searches or len(searches) > 5:
        raise ValueError()
    criteria = []
    allowed = {q(D, 'displayname'), q(C, 'calendar-user-address-set'), q(C, 'calendar-user-type')}
    for search in searches:
        prop = search.find(q(D, 'prop')); match = search.find(q(D, 'match'))
        if prop is None or match is None or len(prop) != 1 or prop[0].tag not in allowed or set(match.attrib) - {'caseless'}:
            raise ValueError()
        criteria.append((prop[0].tag, (match.text or '').casefold()))
    requested_node = root.find(q(D, 'prop'))
    requested = [node.tag for node in requested_node] if requested_node is not None else list(allowed)
    if any(tag not in allowed and tag not in {q(D, 'resourcetype'), q(D, 'principal-URL')} for tag in requested):
        raise ValueError()
    rows = []
    for member in active_members(grant):
        if all(match in _principal_value(member, tag).casefold() for tag, match in criteria):
            rows.append((member_principal_path(grant, member), props_for(grant, member_principal_path(grant, member), 'member-principal', member=member)))
        if len(rows) >= 100:
            break
    return multistatus(rows, requested)


def principal_search_property_set():
    root = element(D, 'principal-search-property-set')
    for namespace, name, description in (
        (D, 'displayname', 'Family member name'),
        (C, 'calendar-user-address-set', 'Family member calendar address'),
        (C, 'calendar-user-type', 'Calendar user type'),
    ):
        item = ET.SubElement(root, q(D, 'principal-search-property'))
        prop = ET.SubElement(item, q(D, 'prop')); prop.append(element(namespace, name))
        ET.SubElement(item, q(D, 'description'), {'{http://www.w3.org/XML/1998/namespace}lang': 'en'}).text = description
    return response(ET.tostring(root, encoding='utf-8', xml_declaration=True))


def _aware(value, zone):
    if isinstance(value, datetime):
        return value.replace(tzinfo=zone) if value.tzinfo is None else value
    if isinstance(value, date):
        return datetime.combine(value, time.min, zone)
    raise ValueError()


def _parse_put(grant, existing, body):
    if not body or len(body) > MAX_BYTES or b'\x00' in body:
        raise ValueError()
    calendar = Calendar.from_ical(body)
    events = calendar.walk('VEVENT')
    if len(events) != 1:
        raise ValueError()
    component = events[0]
    if any(name in component for name in ('RRULE', 'RDATE', 'EXDATE', 'RECURRENCE-ID')):
        raise NotImplementedError()
    if 'DTSTART' not in component:
        raise ValueError()
    zone = family_zone(grant.family)
    raw_start = component.decoded('DTSTART')
    raw_end = component.decoded('DTEND') if 'DTEND' in component else None
    all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)
    start = _aware(raw_start, zone)
    if raw_end is None:
        end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
    else:
        end = _aware(raw_end, zone)
    if end <= start:
        raise ValueError()
    summary = str(component.get('SUMMARY') or '').strip()[:200] or 'Termin'
    payload = dict(existing.payload) if existing is not None and isinstance(existing.payload, dict) else {}
    payload['provider'] = 'FamilyOS'
    uid = str(component.get('UID') or '').strip()
    if uid:
        payload['caldav_uid'] = uid[:255]
    if all_day:
        payload['all_day'] = True
        payload['date_start'] = raw_start.isoformat()
        raw_end_date = raw_end if isinstance(raw_end, date) and not isinstance(raw_end, datetime) else raw_start + timedelta(days=1)
        payload['date_end_exclusive'] = raw_end_date.isoformat()
    else:
        payload.pop('all_day', None); payload.pop('date_start', None); payload.pop('date_end_exclusive', None)
    if 'LOCATION' in component:
        payload['location'] = str(component.get('LOCATION') or '')[:500]
    if 'DESCRIPTION' in component:
        payload['description'] = str(component.get('DESCRIPTION') or '')[:4000]
    participants = attendee_memberships(grant, component)
    return summary, start, end, payload, participants


def _put_event(request, grant, event_id, existing):
    current = event_etag(grant, existing) if existing is not None else None
    if request.headers.get('If-None-Match') == '*' and existing is not None:
        return response(status=412)
    if request.headers.get('If-Match') and request.headers.get('If-Match') != current:
        return response(status=412)
    try:
        title, starts_at, ends_at, payload, participants = _parse_put(grant, existing, request.body)
    except UnknownFamilyAttendee:
        return response(status=409)
    except NotImplementedError:
        return response(status=409)
    except (ValueError, TypeError, KeyError):
        return response(status=400)
    with transaction.atomic():
        locked = FamilyEvent.objects.select_for_update().filter(pk=event_id, family=grant.family).first()
        if existing is None and locked is not None:
            return response(status=412)
        if existing is not None and (locked is None or event_etag(grant, locked) != current):
            return response(status=412)
        if locked is not None and (locked.source_id or locked.external_id or locked.type != 'calendar.event' or not locked.is_family_event):
            return response(status=403)
        if locked is None:
            event = FamilyEvent(id=event_id, family=grant.family, type='calendar.event', title=title,
                                starts_at=starts_at, ends_at=ends_at, actionable=False,
                                payload=payload, is_family_event=True)
            event.save(force_insert=True)
            status = 201
        else:
            event = locked
            event.title = title; event.starts_at = starts_at; event.ends_at = ends_at; event.payload = payload
            event.is_family_event = True
            event.save(update_fields=['title', 'starts_at', 'ends_at', 'payload', 'is_family_event', 'updated_at'])
            status = 204
        event.participants.set(participants)
    result = response(status=status, content_type='text/calendar; charset=utf-8')
    result['ETag'] = event_etag(grant, event)
    return result


def _delete_event(request, grant, existing):
    if existing is None:
        return response(status=404)
    current = event_etag(grant, existing)
    if request.headers.get('If-Match') and request.headers.get('If-Match') != current:
        return response(status=412)
    with transaction.atomic():
        locked = FamilyEvent.objects.select_for_update().filter(pk=existing.pk, family=grant.family).first()
        if locked is None:
            return response(status=404)
        if event_etag(grant, locked) != current:
            return response(status=412)
        if locked.source_id or locked.external_id or locked.type != 'calendar.event' or not locked.is_family_event:
            return response(status=403)
        locked.delete()
    return response(status=204)


@csrf_exempt
def dav(request, path=''):
    blocked = limited(request, request.META.get('REMOTE_ADDR', 'unknown'))
    if blocked:
        return blocked
    grant = authenticate(request)
    if grant is None:
        result = response(status=401); result['WWW-Authenticate'] = 'Basic realm="FamilyOS calendar", charset="UTF-8"'; return result
    principal = f'/caldav/{grant.pk}/principal/'
    principals = f'/caldav/{grant.pk}/principals/'
    home = f'/caldav/{grant.pk}/home/'
    calendar = home + 'family/'
    actual = '/caldav/' + path
    kind = {'/caldav/': 'root', principal: 'principal', principals: 'principal-collection', home: 'home', calendar: 'calendar'}.get(actual)
    member = None
    if kind is None and actual.startswith(principals) and actual.endswith('/'):
        try:
            member_id = UUID(actual[len(principals):-1])
            member = next((row for row in active_members(grant) if row.pk == member_id), None)
            if member is not None:
                kind = 'member-principal'
        except ValueError:
            pass
    event_id = None
    if actual.startswith(calendar) and actual.endswith('.ics'):
        try:
            event_id = UUID(actual[len(calendar):-4])
            kind = 'event'
        except ValueError:
            pass
    if kind is None:
        return response(status=404)
    if request.method not in ('OPTIONS', 'PROPFIND', 'REPORT', 'GET', 'HEAD', 'PUT', 'DELETE'):
        return response(status=403)
    if request.method == 'OPTIONS':
        return response()
    try:
        events = shared_events(grant)
        resources = {}
        def resource(event):
            href = calendar + str(event.pk) + '.ics'
            if href not in resources:
                data = event_data(grant, event); etag = '"' + hashlib.sha256(data).hexdigest() + '"'
                resources[href] = props_for(grant, href, 'event', etag, data)
            return href, resources[href]
        target = next((event for event in events if event.pk == event_id), None) if kind == 'event' else None
        if request.method == 'PUT':
            if kind != 'event':
                return response(status=403)
            return _put_event(request, grant, event_id, target)
        if request.method == 'DELETE':
            if kind != 'event':
                return response(status=403)
            return _delete_event(request, grant, target)
        if kind == 'event' and target is None:
            return response(status=404)
        if request.method in ('GET', 'HEAD'):
            if kind not in ('event', 'calendar'):
                return response(status=405)
            return ics_response(request, grant, [target] if target else events, CALDAV_DETAIL_LEVEL, include_participants=True)
        if request.method == 'PROPFIND':
            depth = request.headers.get('Depth', 'infinity')
            if depth not in ('0', '1'):
                return response(status=403)
            root = xml_body(request) if request.body else element(D, 'propfind')
            if root.tag != q(D, 'propfind') or root.find(q(D, 'propname')) is not None:
                return response(status=400)
            prop = root.find(q(D, 'prop')); requested = [node.tag for node in prop] if prop is not None else None
            stamp = hashlib.sha256(calendar_bytes_with_participants(grant, events, CALDAV_DETAIL_LEVEL)).hexdigest()
            rows = [resource(target)] if target else [(actual, props_for(grant, actual, kind, stamp, member=member))]
            if depth == '1':
                if kind == 'root':
                    rows.append((principal, props_for(grant, principal, 'principal')))
                    rows.append((principals, props_for(grant, principals, 'principal-collection')))
                if kind == 'principal':
                    rows.append((home, props_for(grant, home, 'home')))
                    rows.append((principals, props_for(grant, principals, 'principal-collection')))
                if kind == 'principal-collection':
                    rows.extend((member_principal_path(grant, row), props_for(grant, member_principal_path(grant, row), 'member-principal', member=row)) for row in active_members(grant))
                if kind == 'home': rows.append((calendar, props_for(grant, calendar, 'calendar', stamp)))
                if kind == 'calendar': rows.extend(resource(event) for event in events)
            return multistatus(rows, requested)
        root = xml_body(request)
        if root.tag == q(D, 'principal-property-search') and kind in ('root', 'principal', 'principal-collection'):
            return principal_property_search(root, grant)
        if root.tag == q(D, 'principal-search-property-set') and kind in ('root', 'principal', 'principal-collection'):
            return principal_search_property_set()
        if kind != 'calendar':
            return response(status=403)
        prop = root.find(q(D, 'prop'))
        try:
            requested = report_properties(prop)
        except (ValueError, TypeError):
            return response(status=403)
        if root.tag == q(C, 'calendar-query'):
            bounds = query_range(root)
            selected = events if bounds is None else [event for event in events if overlaps(event, *bounds)]
            return multistatus([resource(event) for event in selected], requested)
        if root.tag == q(C, 'calendar-multiget'):
            hrefs = root.findall(q(D, 'href'))
            if len(hrefs) > 200:
                return response(status=413)
            by_path = {calendar + str(event.pk) + '.ics': event for event in events}; rows = []
            for node in hrefs:
                parsed = urlsplit(node.text or '')
                if parsed.query or parsed.fragment or (parsed.netloc and parsed.netloc != urlsplit(origin()).netloc):
                    return response(status=403)
                href = parsed.path
                if not href.startswith(calendar):
                    return response(status=403)
                rows.append(resource(by_path[href]) if href in by_path else (href, None))
            return multistatus(rows, requested)
        return response(status=403)
    except CalendarCapacityError:
        return response(status=507)
    except (ValueError, TypeError, ET.ParseError, OverflowError):
        return response(status=400)


def well_known(request):
    result = response(status=301); result['Location'] = '/caldav/'; return result
