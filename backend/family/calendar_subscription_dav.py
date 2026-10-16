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

D = 'DAV:'; C = 'urn:ietf:params:xml:ns:caldav'; CS = 'http://calendarserver.org/ns/'
ET.register_namespace('d', D); ET.register_namespace('c', C); ET.register_namespace('cs', CS)

def q(namespace, name): return f'{{{namespace}}}{name}'
def element(namespace, name, text=None): result = ET.Element(q(namespace, name)); result.text = text; return result

def response(data=b'', status=200, content_type='application/xml; charset=utf-8'):
    result = private(HttpResponse(data, status=status, content_type=content_type)); result['DAV'] = '1, calendar-access'; result['Allow'] = 'OPTIONS, PROPFIND, REPORT, GET, HEAD'; return result

def limited(request, identifier):
    decision = enforce('calendar.subscription.read', request=request, identifier=identifier)
    if decision.allowed: return None
    result = response(status=429); result['Retry-After'] = str(decision.retry_after); return result

def ics_response(request, grant, events):
    data = calendar_bytes(grant.family, events, grant.detail_level); etag = '"' + hashlib.sha256(data).hexdigest() + '"'
    result = response(b'' if request.method == 'HEAD' else data, content_type='text/calendar; charset=utf-8')
    if request.headers.get('If-None-Match') in (etag, '*'): result = response(status=304, content_type='text/calendar; charset=utf-8')
    result['ETag'] = etag; result['Content-Disposition'] = 'inline; filename="familyos.ics"'; return result

@csrf_exempt
def feed(request, token):
    if request.method not in ('GET', 'HEAD'): return response(status=405)
    blocked = limited(request, token)
    if blocked: return blocked
    grant = resolve_token(token)
    if grant is None: return response(status=404)
    try: return ics_response(request, grant, shared_events(grant))
    except CalendarCapacityError: return response(status=507)

def authenticate(request):
    header = request.headers.get('Authorization', '')
    try:
        kind, value = header.split(' ', 1)
        if kind.lower() != 'basic' or len(value) > 1024: return None
        username, token = base64.b64decode(value, validate=True).decode('utf-8').split(':', 1)
    except (ValueError, UnicodeError, binascii.Error): return None
    return resolve_token(token, username)

def xml_body(request):
    if int(request.META.get('CONTENT_LENGTH') or 0) > 65536: raise ValueError()
    body = request.body
    if len(body) > 65536 or b'<!' in body or b'\x00' in body: raise ValueError()
    root = ET.fromstring(body)
    def bounded(node, depth=0):
        if depth > 12 or len(list(root.iter())) > 1000: raise ValueError()
        for child in node: bounded(child, depth + 1)
    bounded(root); return root

def props_for(grant, path, kind, etag=None, data=None):
    principal = f'/caldav/{grant.pk}/principal/'; home = f'/caldav/{grant.pk}/home/'; values = {}
    def add(ns, name, text=None, child=None):
        value = element(ns, name, text)
        if child is not None: value.append(child)
        values[q(ns, name)] = value; return value
    resource = add(D, 'resourcetype')
    if kind != 'event': resource.append(element(D, 'collection'))
    if kind == 'principal': resource.append(element(D, 'principal'))
    if kind == 'calendar': resource.append(element(C, 'calendar'))
    if kind == 'root': add(D, 'current-user-principal', child=element(D, 'href', principal))
    if kind == 'principal':
        add(D, 'displayname', 'FamilyOS calendar subscription'); add(C, 'calendar-home-set', child=element(D, 'href', home)); add(D, 'principal-URL', child=element(D, 'href', principal))
    if kind == 'home': add(D, 'displayname', 'FamilyOS')
    if kind == 'calendar':
        add(D, 'displayname', grant.family.name); add(C, 'calendar-description', 'FamilyOS read-only family calendar'); add(C, 'supported-calendar-component-set', child=ET.Element(q(C, 'comp'), {'name': 'VEVENT'})); add(CS, 'getctag', etag or '')
    if kind == 'event':
        add(D, 'getetag', etag); add(D, 'getcontenttype', 'text/calendar; component=vevent');
        if data is not None: add(C, 'calendar-data', data.decode('utf-8'))
    return values

def multistatus(rows):
    root = ET.Element(q(D, 'multistatus'))
    for href, props in rows:
        item = ET.SubElement(root, q(D, 'response')); ET.SubElement(item, q(D, 'href')).text = href; stat = ET.SubElement(item, q(D, 'propstat')); prop = ET.SubElement(stat, q(D, 'prop'))
        for value in props: prop.append(value)
        ET.SubElement(stat, q(D, 'status')).text = 'HTTP/1.1 200 OK'
    return ET.tostring(root, xml_declaration=True, encoding='utf-8')

def event_data(grant, event): return calendar_bytes(grant.family, [event], grant.detail_level)
def event_etag(grant, event): return '"' + hashlib.sha256(event_data(grant, event)).hexdigest() + '"'

def dav(request, path=''):
    if request.method == 'OPTIONS': return response(status=200)
    grant = authenticate(request)
    if grant is None:
        result = response(status=401); result['WWW-Authenticate'] = 'Basic realm="FamilyOS Calendar"'; return result
    blocked = limited(request, str(grant.pk))
    if blocked: return blocked
    base = f'/caldav/{grant.pk}/'; full = '/' + path.strip('/') + '/' if path else '/'; requested = request.path
    if request.method in ('GET', 'HEAD'):
        try:
            event_id = UUID(path.strip('/').split('/')[-1].removesuffix('.ics')); event = next((row for row in shared_events(grant) if row.pk == event_id), None)
            if event is None: return response(status=404)
            return ics_response(request, grant, [event])
        except (ValueError, IndexError): return response(status=404)
    if request.method not in ('PROPFIND', 'REPORT'): return response(status=405)
    try: root = xml_body(request) if request.body else ET.Element(q(D, 'propfind'))
    except (ValueError, ET.ParseError): return response(status=400)
    events = shared_events(grant); rows = []
    if request.method == 'REPORT':
        timerange = root.find('.//' + q(C, 'time-range')); start = end = None
        try:
            if timerange is not None:
                start = datetime.strptime(timerange.get('start'), '%Y%m%dT%H%M%SZ').replace(tzinfo=dt_timezone.utc) if timerange.get('start') else None
                end = datetime.strptime(timerange.get('end'), '%Y%m%dT%H%M%SZ').replace(tzinfo=dt_timezone.utc) if timerange.get('end') else None
        except ValueError: return response(status=400)
        events = [event for event in events if overlaps(event, start, end)]
        for event in events:
            href = f'{base}home/family/{event.pk}.ics'; data = event_data(grant, event); rows.append((href, props_for(grant, href, 'event', event_etag(grant, event), data).values()))
    else:
        kind = 'root'
        if path.startswith(str(grant.pk) + '/principal'): kind = 'principal'
        elif path.startswith(str(grant.pk) + '/home/family'): kind = 'calendar'
        elif path.startswith(str(grant.pk) + '/home'): kind = 'home'
        rows.append((requested, props_for(grant, requested, kind).values()))
    try: return response(multistatus(rows), status=207)
    except CalendarCapacityError: return response(status=507)
