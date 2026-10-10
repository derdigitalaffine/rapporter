"""Private, versioned Today layouts. Layouts contain presentation settings only."""
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Family, Membership, TodayLayout

LEGACY_WIDGET_IDS = ('weather', 'priority', 'waste', 'next', 'tasks', 'shopping', 'routines', 'birthdays', 'notes')
PRE_PINBOARD_WIDGET_IDS = LEGACY_WIDGET_IDS + ('loyalty', 'inbox')
WIDGET_IDS = PRE_PINBOARD_WIDGET_IDS + ('week', 'pinboard')
DEFAULT_WEEK_SETTINGS = {'events': True, 'waste': True, 'holidays': True, 'special': True}
DEFAULT_WIDGET_ORDER = ('week', 'priority', 'next', 'pinboard', 'weather', 'tasks', 'shopping', 'routines', 'waste', 'inbox', 'birthdays', 'notes', 'loyalty')


def _default_widget(key, *, visible=True):
    row = {'id': key, 'visible': visible, 'size': 'full'}
    if key == 'week':
        row['settings'] = deepcopy(DEFAULT_WEEK_SETTINGS)
    return row


DEFAULT_WIDGETS = [_default_widget(key) for key in DEFAULT_WIDGET_ORDER]


def _normalize_saved_widget(row):
    if not isinstance(row, dict):
        return row
    clean = deepcopy(row)
    if clean.get('id') == 'week':
        supplied = clean.get('settings') if isinstance(clean.get('settings'), dict) else {}
        clean['settings'] = {key: supplied.get(key, value) if type(supplied.get(key, value)) is bool else value for key, value in DEFAULT_WEEK_SETTINGS.items()}
    else:
        clean.pop('settings', None)
    return clean


def _expanded_widgets(widgets):
    """Preserve saved choices while introducing the week/pinboard surfaces safely."""
    rows = [_normalize_saved_widget(row) for row in deepcopy(widgets)]
    seen = {row.get('id') for row in rows if isinstance(row, dict)}
    # The old week strip was always visible in the Today header. Move that information
    # into the configurable widget without making it disappear for existing users.
    if 'week' not in seen:
        rows.insert(0, _default_widget('week', visible=True))
        seen.add('week')
    # Pinnwand is a deliberate prominent replacement for the old board entry point.
    if 'pinboard' not in seen:
        index = next((idx + 1 for idx, row in enumerate(rows) if row.get('id') == 'next'), min(4, len(rows)))
        rows.insert(index, _default_widget('pinboard', visible=True))
        seen.add('pinboard')
    # Older releases already used this policy for later optional Today widgets.
    for key in PRE_PINBOARD_WIDGET_IDS:
        if key not in seen:
            rows.append(_default_widget(key, visible=False))
            seen.add(key)
    return rows


def payload(layout=None):
    widgets = _expanded_widgets(layout.widgets) if layout else deepcopy(DEFAULT_WIDGETS)
    return {'version': 1, 'revision': layout.revision if layout else 0, 'widgets': widgets}


def _validate_widget(widget, seen):
    if not isinstance(widget, dict):
        return False
    allowed = {'id', 'visible', 'size'} | ({'settings'} if widget.get('id') == 'week' else set())
    if set(widget) - allowed or not {'id', 'visible', 'size'} <= set(widget):
        return False
    key = widget['id']
    if not isinstance(key, str) or key not in WIDGET_IDS or key in seen:
        return False
    if type(widget['visible']) is not bool or widget['size'] not in ('full', 'compact'):
        return False
    if key == 'week':
        settings = widget.get('settings', DEFAULT_WEEK_SETTINGS)
        if not isinstance(settings, dict) or set(settings) != set(DEFAULT_WEEK_SETTINGS) or any(type(value) is not bool for value in settings.values()):
            return False
    elif 'settings' in widget:
        return False
    seen.add(key)
    return True


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def today_layout(request):
    family_id = request.query_params.get('family')
    try:
        family = Family.objects.filter(id=family_id, memberships__user=request.user).first() if family_id else None
    except (ValidationError, ValueError, TypeError):
        family = None
    if not family:
        return Response({'detail': 'Family not found.'}, status=404)
    if request.method == 'GET':
        return Response(payload(TodayLayout.objects.filter(family=family, user=request.user).first()))
    data = request.data
    if not isinstance(data, dict) or set(data) != {'version', 'revision', 'widgets'}:
        return Response({'detail': 'Expected version, revision and widgets.'}, status=400)
    if type(data['version']) is not int or data['version'] != 1 or type(data['revision']) is not int or data['revision'] < 0:
        return Response({'detail': 'Invalid layout version or revision.'}, status=400)
    widgets = data['widgets']
    if not isinstance(widgets, list) or not len(LEGACY_WIDGET_IDS) <= len(widgets) <= len(WIDGET_IDS):
        return Response({'detail': 'Supply supported widgets exactly once.'}, status=400)
    seen = set()
    if not all(_validate_widget(widget, seen) for widget in widgets) or any(key not in seen for key in LEGACY_WIDGET_IDS):
        return Response({'detail': 'Invalid widget configuration.'}, status=400)
    normalized = _expanded_widgets(widgets)
    with transaction.atomic():
        Membership.objects.select_for_update().get(family=family, user=request.user)
        layout = TodayLayout.objects.filter(family=family, user=request.user).first()
        if data['revision'] != (layout.revision if layout else 0):
            return Response({'detail': 'Layout changed on another device.', 'current': payload(layout)}, status=409)
        if not layout:
            layout = TodayLayout(family=family, user=request.user)
        layout.widgets = normalized
        layout.revision += 1
        layout.save()
    return Response(payload(layout))
