"""Bounded read-only CalDAV subset: discovery, ETag listing, query/multiget, GET.

No scheduling, ACL mutations, sync-token or write capability is advertised.
"""
import base64
import binascii
import hashlib
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlsplit
from uuid import UUID
from xml.etree import ElementTree as ET
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from auth_abuse.service import enforce
from .calendar_subscription_service import resolve_token, origin
from .calendar_subscription_ics import shared_events, calendar_bytes, overlaps, CalendarCapacityError, MAX_BYTES
from .calendar_subscription_views import private

D = 'DAV:'
C = 'urn:ietf:params:xml:ns:caldav'
CS = 'http://calendarserver.org/ns/'
ET.register_namespace('d', D); ET.register_namespace('c', C); ET.register_namespace('cs', CS)

def q(namespace, name):
    return f'{{{namespace}}}{name}'


def element(namespace, name, text=None):
    result = ET.Element(q(namespace, name)); result.text = text
    return result


def response(data=b'', status=200, content_type='application/xml; charset=utf-8'):
    result = private(HttpResponse(data, status=status, content_type=content_type))
    result['DAV'] = '1, calendar-access'
    result['Allow'] = 'OPTIONS, PROPFIND, REPORT, GET, HEAD'
    return result


def limited(request, identifier):
    decision = enforce('calendar.subscription.read', request=request, identifier=identifier)
    if decision.allowed:
        return None
    result = response(status=429); result['Retry-After'] = str(decision.retry_after)
    return result


def ics_response(request, grant, events):
    data = calendar_bytes(grant.family, events, grant.detail_level)
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


def props_for(grant, path, kind, etag=None, data=None):
    principal = f'/caldav/{grant.pk}/principal/'
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
    if kind == 'principal':
        resource.append(element(D, 'principal'))
    if kind == 'calendar':
        resource.append(element(C, 'calendar'))
    add(D, 'displayname', grant.family.name if kind == 'calendar' else 'FamilyOS')
    add(D, 'current-user-principal', child=element(D, 'href', principal))
    add(D, 'principal-URL', child=element(D, 'href', principal))
    add(C, 'calendar-home-set', child=element(D, 'href', home))
    add(D, 'owner', child=element(D, 'href', principal))
    privileges = add(D, 'current-user-privilege-set')
    privilege = ET.SubElement(privileges, q(D, 'privilege')); privilege.append(element(D, 'read'))
    reports = add(D, 'supported-report-set')
    if kind == 'calendar':
        for name in ('calendar-query', 'calendar-multiget'):
            supported = ET.SubElement(reports, q(D, 'supported-report')); report = ET.SubElement(supported, q(D, 'report')); report.append(element(C, name))
        components = add(C, 'supported-calendar-component-set'); ET.SubElement(components, q(C, 'comp'), {'name': 'VEVENT'})
        formats = add(C, 'supported-calendar-data'); ET.SubElement(formats, q(C, 'calendar-data'), {'content-type': 'text/calendar', 'version': '2.0'})
        add(CS, 'getctag', etag)
        add(C, 'max-resource-size', str(8 * 1024 * 1024))
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


@csrf_exempt
def dav(request, path=''):
    blocked = limited(request, request.META.get('REMOTE_ADDR', 'unknown'))
    if blocked:
        return blocked
    grant = authenticate(request)
    if grant is None:
        result = response(status=401); result['WWW-Authenticate'] = 'Basic realm="FamilyOS calendar", charset="UTF-8"'; return result
    principal = f'/caldav/{grant.pk}/principal/'
    home = f'/caldav/{grant.pk}/home/'
    calendar = home + 'family/'
    actual = '/caldav/' + path
    kind = {'/caldav/': 'root', principal: 'principal', home: 'home', calendar: 'calendar'}.get(actual)
    event_id = None
    if actual.startswith(calendar) and actual.endswith('.ics'):
        try:
            event_id = UUID(actual[len(calendar):-4])
            kind = 'event'
        except ValueError:
            pass
    if kind is None:
        return response(status=404)
    if request.method not in ('OPTIONS', 'PROPFIND', 'REPORT', 'GET', 'HEAD'):
        return response(status=403)
    if request.method == 'OPTIONS':
        return response()
    try:
        events = shared_events(grant)
        resources = {}
        def resource(event):
            href = calendar + str(event.pk) + '.ics'
            if href not in resources:
                data = calendar_bytes(grant.family, [event], grant.detail_level); etag = '"' + hashlib.sha256(data).hexdigest() + '"'
                resources[href] = props_for(grant, href, 'event', etag, data)
            return href, resources[href]
        target = next((event for event in events if event.pk == event_id), None) if kind == 'event' else None
        if kind == 'event' and target is None:
            return response(status=404)
        if request.method in ('GET', 'HEAD'):
            if kind not in ('event', 'calendar'):
                return response(status=405)
            return ics_response(request, grant, [target] if target else events)
        if request.method == 'PROPFIND':
            depth = request.headers.get('Depth', 'infinity')
            if depth not in ('0', '1'):
                return response(status=403)
            root = xml_body(request) if request.body else element(D, 'propfind')
            if root.tag != q(D, 'propfind') or root.find(q(D, 'propname')) is not None:
                return response(status=400)
            prop = root.find(q(D, 'prop')); requested = [node.tag for node in prop] if prop is not None else None
            stamp = hashlib.sha256(calendar_bytes(grant.family, events, grant.detail_level)).hexdigest()
            rows = [resource(target)] if target else [(actual, props_for(grant, actual, kind, stamp))]
            if depth == '1':
                if kind == 'root': rows.append((principal, props_for(grant, principal, 'principal')))
                if kind == 'principal': rows.append((home, props_for(grant, home, 'home')))
                if kind == 'home': rows.append((calendar, props_for(grant, calendar, 'calendar', stamp)))
                if kind == 'calendar': rows.extend(resource(event) for event in events)
            return multistatus(rows, requested)
        if kind != 'calendar':
            return response(status=403)
        root = xml_body(request)
        prop = root.find(q(D, 'prop')); requested = [node.tag for node in prop] if prop is not None else [q(D, 'getetag'), q(C, 'calendar-data')]
        if any(list(node) or node.attrib for node in (prop if prop is not None else [])):
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
