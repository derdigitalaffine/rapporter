"""Canonical Today 2.0 widget registry and presentation-only layout metadata."""
from copy import deepcopy

TODAY_LAYOUT_VERSION = 2
TODAY_WIDGET_SIZES = ('compact', 'medium', 'wide')
LEGACY_SIZE_MAP = {'compact': 'compact', 'square': 'medium', 'full': 'wide'}
DEPRECATED_TODO_WIDGET_IDS = frozenset(('tasks', 'routines'))

DEFAULT_WEEK_SETTINGS = {'events': True, 'waste': True, 'holidays': True, 'special': True}
DEFAULT_TRIP_SETTINGS = {'show_wishes': False}


def _entry(
    key,
    order,
    *,
    component='external',
    category='family',
    sizes=('compact', 'wide'),
    default_size='wide',
    settings=None,
    deep_link=None,
):
    if default_size not in sizes:
        raise ValueError(f'Default size {default_size!r} is not supported by {key!r}.')
    return {
        'id': key,
        'titleKey': key,
        'category': category,
        'component': component,
        'defaultVisible': True,
        'defaultOrder': order,
        'defaultSize': default_size,
        'supportedSizes': tuple(sizes),
        'moduleGate': None,
        'permissionGate': None,
        'sensitivity': 'family',
        'refreshPolicy': 'on-focus',
        'emptyStatePolicy': 'render',
        'deepLink': deep_link,
        'settingsSchema': deepcopy(settings) if settings else None,
    }


TODAY_WIDGET_REGISTRY = (
    _entry('week', 0, component='WeekCompassWidget', category='planning', settings=DEFAULT_WEEK_SETTINGS),
    _entry('priority', 1, category='planning'),
    _entry('trip', 2, category='planning', sizes=TODAY_WIDGET_SIZES, default_size='medium', settings=DEFAULT_TRIP_SETTINGS),
    _entry('next', 3, category='planning', sizes=TODAY_WIDGET_SIZES, default_size='medium'),
    _entry('pinboard', 4, component='PinboardTodayWidget', category='collaboration', default_size='compact'),
    _entry('weather', 5, category='context', sizes=TODAY_WIDGET_SIZES, default_size='medium'),
    _entry('todo', 6, component='TodayTodoWidget', category='planning'),
    _entry('shopping', 7, category='household', default_size='compact'),
    _entry('waste', 8, category='household', sizes=TODAY_WIDGET_SIZES, default_size='medium'),
    _entry('inbox', 9, category='collaboration', sizes=TODAY_WIDGET_SIZES, default_size='medium'),
    _entry('birthdays', 10, category='family', sizes=TODAY_WIDGET_SIZES, default_size='medium'),
    _entry('notes', 11, category='family', sizes=TODAY_WIDGET_SIZES, default_size='medium'),
    _entry('loyalty', 12, category='household', sizes=TODAY_WIDGET_SIZES, default_size='compact'),
)

TODAY_WIDGETS_BY_ID = {entry['id']: entry for entry in TODAY_WIDGET_REGISTRY}
DEFAULT_WIDGET_ORDER = tuple(entry['id'] for entry in TODAY_WIDGET_REGISTRY)
DEFAULT_WIDGET_SETTINGS = {
    entry['id']: deepcopy(entry['settingsSchema'])
    for entry in TODAY_WIDGET_REGISTRY
    if entry['settingsSchema'] is not None
}


def widget_settings(key):
    settings = DEFAULT_WIDGET_SETTINGS.get(key)
    return deepcopy(settings) if settings is not None else None


def default_widget(key, *, visible=None):
    entry = TODAY_WIDGETS_BY_ID[key]
    row = {
        'id': key,
        'visible': entry['defaultVisible'] if visible is None else visible,
        'size': entry['defaultSize'],
    }
    settings = widget_settings(key)
    if settings is not None:
        row['settings'] = settings
    return row


DEFAULT_WIDGETS = [default_widget(key) for key in DEFAULT_WIDGET_ORDER]
