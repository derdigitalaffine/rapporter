"""Private, versioned Today layouts. Layouts contain presentation settings only."""
from copy import deepcopy
import re

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Family, Membership, TodayLayout
from .today_layout_registry import (
    DEFAULT_TRIP_SETTINGS,
    DEFAULT_WEEK_SETTINGS,
    DEFAULT_WIDGET_ORDER,
    DEFAULT_WIDGET_SETTINGS,
    DEFAULT_WIDGETS,
    DEPRECATED_TODO_WIDGET_IDS,
    LEGACY_CORE_WIDGET_ALIASES,
    LEGACY_SIZE_MAP,
    TODAY_LAYOUT_VERSION,
    TODAY_WIDGET_REGISTRY,
    TODAY_WIDGET_SIZES,
    TODAY_WIDGETS_BY_ID,
    default_widget,
)

# Keep accepting the original split Task/Routine and priority/next ids so stale
# clients and stored personal layouts migrate without losing order/visibility.
LEGACY_WIDGET_IDS = ('weather', 'priority', 'waste', 'next', 'tasks', 'shopping', 'routines', 'birthdays', 'notes')
LEGACY_TODO_SIZE_SUPPORT = {
    'tasks': frozenset(('compact', 'wide')),
    'routines': frozenset(TODAY_WIDGET_SIZES),
}
REQUIRED_STABLE_WIDGET_IDS = frozenset(key for key in LEGACY_WIDGET_IDS if key not in DEPRECATED_TODO_WIDGET_IDS)
SAFE_WIDGET_ID = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
MAX_WIDGETS = 64


def _valid_widget_id(key):
    return isinstance(key, str) and SAFE_WIDGET_ID.fullmatch(key) is not None


def _semantic_size(size):
    if size in TODAY_WIDGET_SIZES:
        return size
    return LEGACY_SIZE_MAP.get(size)


def _normalize_settings(key, supplied):
    defaults = DEFAULT_WIDGET_SETTINGS.get(key)
    if defaults is None:
        return None
    supplied = supplied if isinstance(supplied, dict) else {}
    return {
        name: supplied.get(name, value) if type(supplied.get(name, value)) is bool else value
        for name, value in defaults.items()
    }


def _normalize_saved_widget(row):
    """Sanitize persisted rows to the presentation-only v2 contract."""
    if not isinstance(row, dict):
        return None
    key = row.get('id')
    if not _valid_widget_id(key) or type(row.get('visible')) is not bool:
        return None
    size = _semantic_size(row.get('size'))
    if size is None:
        return None
    entry = TODAY_WIDGETS_BY_ID.get(key)
    if entry is not None and size not in entry['supportedSizes']:
        size = entry['defaultSize']
    if key in LEGACY_TODO_SIZE_SUPPORT and size not in LEGACY_TODO_SIZE_SUPPORT[key]:
        size = 'wide'
    clean = {'id': key, 'visible': row['visible'], 'size': size}
    settings = _normalize_settings(key, row.get('settings'))
    if settings is not None:
        clean['settings'] = settings
    return clean


def _migrate_core_widgets(rows):
    """Replace priority/next aliases in place while preserving user layout choices."""
    canonical = {row['id'] for row in rows if row['id'] not in LEGACY_CORE_WIDGET_ALIASES}
    migrated = []
    for row in rows:
        target = LEGACY_CORE_WIDGET_ALIASES.get(row['id'])
        if target is None:
            migrated.append(row)
            continue
        if target in canonical:
            continue
        entry = TODAY_WIDGETS_BY_ID[target]
        size = row['size'] if row['size'] in entry['supportedSizes'] else entry['defaultSize']
        migrated.append({'id': target, 'visible': row['visible'], 'size': size})
        canonical.add(target)
    return migrated


def _migrate_todo_widgets(rows):
    """Collapse the former Tasks/Routines cards into one canonical To-do card."""
    todo = next((row for row in rows if row.get('id') == 'todo'), None)
    legacy = [(index, row) for index, row in enumerate(rows) if row.get('id') in DEPRECATED_TODO_WIDGET_IDS]
    if todo is not None:
        return [row for row in rows if row.get('id') not in DEPRECATED_TODO_WIDGET_IDS]
    if not legacy:
        return rows

    legacy_rows = [row for _, row in legacy]
    visible = any(row.get('visible') is True for row in legacy_rows)
    tasks_row = next((row for row in legacy_rows if row.get('id') == 'tasks'), None)
    preferred = tasks_row.get('size') if tasks_row and tasks_row.get('size') in TODAY_WIDGET_SIZES else None
    if preferred is None:
        preferred = next((row.get('size') for row in legacy_rows if row.get('size') in TODAY_WIDGET_SIZES), TODAY_WIDGETS_BY_ID['todo']['defaultSize'])
    if preferred not in TODAY_WIDGETS_BY_ID['todo']['supportedSizes']:
        preferred = TODAY_WIDGETS_BY_ID['todo']['defaultSize']
    combined = {'id': 'todo', 'visible': visible, 'size': preferred}
    first = min(index for index, _ in legacy)
    cleaned = [row for row in rows if row.get('id') not in DEPRECATED_TODO_WIDGET_IDS]
    insert_at = sum(1 for row in rows[:first] if row.get('id') not in DEPRECATED_TODO_WIDGET_IDS)
    cleaned.insert(insert_at, combined)
    return cleaned


def _expanded_widgets(widgets, *, legacy_defaults=True):
    """Migrate to v2 while preserving order, visibility and unknown widget rows."""
    rows = []
    seen = set()
    for raw in deepcopy(widgets):
        row = _normalize_saved_widget(raw)
        if row is None or row['id'] in seen:
            continue
        seen.add(row['id'])
        rows.append(row)
    rows = _migrate_todo_widgets(_migrate_core_widgets(rows))
    seen = {row['id'] for row in rows}

    # These surfaces were introduced after the original v1 layout. Existing v1
    # users historically received them visible at deterministic insertion points.
    if 'week' not in seen:
        timeline_index = next((index for index, row in enumerate(rows) if row['id'] == 'timeline'), None)
        rows.insert(timeline_index + 1 if timeline_index is not None else 0, default_widget('week', visible=legacy_defaults))
        seen.add('week')
    if 'trip' not in seen:
        focus_index = next((index for index, row in enumerate(rows) if row['id'] == 'focus'), None)
        rows.insert(focus_index + 1 if focus_index is not None else min(1, len(rows)), default_widget('trip', visible=legacy_defaults))
        seen.add('trip')
    if 'pinboard' not in seen:
        timeline_index = next((index for index, row in enumerate(rows) if row['id'] == 'timeline'), None)
        rows.insert(timeline_index + 1 if timeline_index is not None else min(5, len(rows)), default_widget('pinboard', visible=legacy_defaults))
        seen.add('pinboard')

    # Registry growth is additive. Missing modern widgets are retained as hidden
    # rows so enabling a module later never rewrites a user's saved choices.
    for entry in TODAY_WIDGET_REGISTRY:
        key = entry['id']
        if key not in seen:
            # Games is the explicit #521 registry introduction. Saved rows above,
            # including an explicitly hidden Games widget, are never overwritten.
            rows.append(default_widget(key, visible=TODAY_WIDGETS_BY_ID[key]['defaultVisible'] if key == 'games' else False))
            seen.add(key)
    return rows


def payload(layout=None):
    widgets = _expanded_widgets(layout.widgets, legacy_defaults=True) if layout else deepcopy(DEFAULT_WIDGETS)
    return {'version': TODAY_LAYOUT_VERSION, 'revision': layout.revision if layout else 0, 'widgets': widgets}


def _validate_widget(widget, seen, *, version):
    if not isinstance(widget, dict):
        return False
    key = widget.get('id')
    if not _valid_widget_id(key) or key in seen:
        return False
    defaults = DEFAULT_WIDGET_SETTINGS.get(key)
    allowed = {'id', 'visible', 'size'} | ({'settings'} if defaults is not None else set())
    if set(widget) - allowed or not {'id', 'visible', 'size'} <= set(widget):
        return False
    if type(widget['visible']) is not bool:
        return False

    raw_size = widget['size']
    if version == 1:
        if raw_size not in LEGACY_SIZE_MAP:
            return False
        size = LEGACY_SIZE_MAP[raw_size]
    else:
        if raw_size not in TODAY_WIDGET_SIZES:
            return False
        size = raw_size

    entry = TODAY_WIDGETS_BY_ID.get(key)
    if entry is not None and size not in entry['supportedSizes']:
        return False
    if key in LEGACY_TODO_SIZE_SUPPORT and size not in LEGACY_TODO_SIZE_SUPPORT[key]:
        return False
    if key in DEPRECATED_TODO_WIDGET_IDS and version != 1:
        return False

    if defaults is not None:
        settings = widget.get('settings', defaults)
        if (not isinstance(settings, dict) or set(settings) != set(defaults) or
                any(type(value) is not bool for value in settings.values())):
            return False
    elif 'settings' in widget:
        # Unknown/disabled widgets survive, but may never carry arbitrary domain
        # payloads through the layout endpoint.
        return False
    seen.add(key)
    return True


def _has_required_v1_widgets(seen):
    has_todo_shape = 'todo' in seen or DEPRECATED_TODO_WIDGET_IDS <= seen
    return REQUIRED_STABLE_WIDGET_IDS <= seen and has_todo_shape


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
    if (type(data['version']) is not int or data['version'] not in (1, TODAY_LAYOUT_VERSION) or
            type(data['revision']) is not int or data['revision'] < 0):
        return Response({'detail': 'Invalid layout version or revision.'}, status=400)
    widgets = data['widgets']
    if not isinstance(widgets, list) or not 1 <= len(widgets) <= MAX_WIDGETS:
        return Response({'detail': 'Supply a bounded widget layout.'}, status=400)
    seen = set()
    if not all(_validate_widget(widget, seen, version=data['version']) for widget in widgets):
        return Response({'detail': 'Invalid widget configuration.'}, status=400)
    if data['version'] == 1 and not _has_required_v1_widgets(seen):
        return Response({'detail': 'Invalid legacy widget configuration.'}, status=400)

    normalized = _expanded_widgets(widgets, legacy_defaults=data['version'] == 1)
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
