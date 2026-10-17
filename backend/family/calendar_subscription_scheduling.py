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
    if request.method != 'PROPFIND' or path != principal:
        return None
    depth = request.headers.get('Depth', 'infinity')
    if depth not in ('0', '1'):
        return _scheduled(core.response(status=403))
    try:
        root = core.xml_body(request) if request.body else core.element(D, 'propfind')
    except (ValueError, TypeError, ET.ParseError, OverflowError):
        return _scheduled(core.response(status=400))
    if root.tag != core.q(D, 'propfind') or root.find(core.q(D, 'propname')) is not None:
        return None
    prop = root.find(core.q(D, 'prop'))
    if prop is None:
        return None
    requested = [node.tag for node in prop]
    schedule_names = {core.q(C, 'schedule-inbox-URL'), core.q(C, 'schedule-outbox-URL')}
    if not schedule_names.intersection(requested):
        return None

    home = f'/caldav/{grant.pk}/home/'
    principals = f'/caldav/{grant.pk}/principals/'
    values = core.props_for(grant, principal, 'principal')
    values[core.q(C, 'schedule-inbox-URL')] = _href_property('schedule-inbox-URL', home + 'inbox/')
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


@csrf_exempt
def dav(request, path=''):
    actual = '/caldav/' + path
    # Scheduling resources need authentication before the core DAV router because
    # they are intentionally not regular calendar collections.
    if request.method == 'PROPFIND' or actual.endswith('/inbox/') or actual.endswith('/outbox/'):
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
        principal = _principal_propfind(request, grant, actual)
        if principal is not None:
            return principal
        # Avoid charging the same request twice when delegating after an
        # authenticated PROPFIND.
        original_limited = core.limited
        original_authenticate = core.authenticate
        core.limited = lambda _request, _identifier: None
        core.authenticate = lambda _request: grant
        try:
            result = core.dav(request, path)
        finally:
            core.limited = original_limited
            core.authenticate = original_authenticate
        return _scheduled(result)

    result = core.dav(request, path)
    return _scheduled(result)
