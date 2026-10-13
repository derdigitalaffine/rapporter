"""Canonical Today 2.0 widget registry and presentation-only layout metadata."""
from copy import deepcopy

TODAY_LAYOUT_VERSION = 2
TODAY_WIDGET_SIZES = ('compact', 'medium', 'wide')
LEGACY_SIZE_MAP = {'compact': 'compact', 'square': 'medium', 'full': 'wide'}
DEPRECATED_TODO_WIDGET_IDS = frozenset(('tasks', 'routines'))
LEGACY_CORE_WIDGET_ALIASES = {'priority': 'focus', 'next': 'timeline'}

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
    default_visible=True,
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
        'defaultVisible': default_visible,
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
    _entry('situation', 0, component='TodaySituation', category='planning', sizes=('compact', 'medium'), default_size='compact'),
    _entry('focus', 1, component='TodayFocusWidget', category='planning', default_size='wide'),
    _entry('timeline', 2, component='TodayTimelineWidget', category='planning', sizes=TODAY_WIDGET_SIZES, default_size='wide'),
    _entry('week', 3, component='WeekCompassWidget', category='planning', sizes=TODAY_WIDGET_SIZES, default_size='medium', settings=DEFAULT_WEEK_SETTINGS),
    _entry('todo', 4, component='TodayTodoWidget', category='planning', sizes=TODAY_WIDGET_SIZES, default_size='compact'),
    _entry('quick-actions', 5, component='TodayQuickActionsWidget', category='planning', sizes=('compact', 'wide'), default_size='compact'),
    _entry('pinboard', 6, component='PinboardTodayWidget', category='collaboration', sizes=TODAY_WIDGET_SIZES, default_size='medium'),
    _entry('tomorrow', 7, component='TodayTomorrowWidget', category='planning', sizes=('compact', 'medium'), default_size='compact', default_visible=False),
    _entry('family-load', 8, component='TodayFamilyLoadWidget', category='family', sizes=('compact', 'medium'), default_size='compact', default_visible=False),
    _entry('trip', 9, category='planning', sizes=TODAY_WIDGET_SIZES, default_size='medium', default_visible=False, settings=DEFAULT_TRIP_SETTINGS),
    _entry('weather', 10, category='context', sizes=TODAY_WIDGET_SIZES, default_size='medium', default_visible=False),
    _entry('shopping', 11, category='household', default_size='compact', default_visible=False),
    _entry('waste', 12, category='household', sizes=TODAY_WIDGET_SIZES, default_size='medium', default_visible=False),
    _entry('inbox', 13, category='collaboration', sizes=TODAY_WIDGET_SIZES, default_size='medium', default_visible=False),
    _entry('games', 14, component='GamesTodayWidget', category='collaboration', sizes=TODAY_WIDGET_SIZES, default_size='medium', deep_link='/?page=games'),
    _entry('birthdays', 15, sizes=TODAY_WIDGET_SIZES, default_size='medium', default_visible=False),
    _entry('notes', 16, sizes=TODAY_WIDGET_SIZES, default_size='medium', default_visible=False),
    _entry('loyalty', 17, category='household', sizes=TODAY_WIDGET_SIZES, default_size='compact', default_visible=False),
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
