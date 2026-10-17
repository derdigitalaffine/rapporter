"""Minimal CalDAV scheduling facade for FamilyOS-internal participants.

FamilyOS does not deliver email invitations. Scheduling is limited to active
members of the authenticated family and maps to the shared FamilyEvent participant
set. The outbox acknowledges internal iTIP messages so native clients can expose
invitee editing without claiming external delivery.
"""
from xml.etree import ElementTree as ET

from django.views.decorators.csrf import csrf_exempt
from icalendar import Calendar

from . import calendar_subscription_dav as core
from .calendar_subscription_ics import MAX_BYTES
from .calendar_subscription_participants import UnknownFamilyAttendee, attendee_memberships

D = core.D
C = core.C


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

    schedule_match = request.META.get('HTTP_IF_SCHEDULE_TAG_MATCH')
    if schedule_match and not request.META.get('HTTP_IF_MATCH'):
        request.META['HTTP_IF_MATCH'] = schedule_match
    return _apply_schedule_tag(request, _scheduled(core.dav(request, path)))
