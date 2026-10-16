from copy import deepcopy

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, TodayLayout
from .today_layout_registry import (
    DEFAULT_TRIP_SETTINGS,
    DEFAULT_WEEK_SETTINGS,
    DEFAULT_WIDGET_ORDER,
    DEFAULT_WIDGETS,
    TODAY_LAYOUT_VERSION,
    TODAY_WIDGET_REGISTRY,
)
from .today_layout_views import LEGACY_WIDGET_IDS


class TodayLayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='widget-owner')
        self.other = get_user_model().objects.create_user(username='widget-other')
        self.family = Family.objects.create(name='Widgets', slug='widgets')
        self.foreign = Family.objects.create(name='Foreign', slug='widgets-foreign')
        Membership.objects.create(user=self.user, family=self.family, role='owner')
        Membership.objects.create(user=self.other, family=self.family, role='child')
        Membership.objects.create(user=self.other, family=self.foreign, role='owner')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f'/api/today-layout/?family={self.family.id}'

    def current_v1_payload(self, revision=0):
        ids = ['week', *LEGACY_WIDGET_IDS, 'trip', 'pinboard']
        widgets = []
        for key in ids:
            if any(row['id'] == key for row in widgets):
                continue
            widgets.append({'id': key, 'visible': True, 'size': 'full'})
        return {'version': 1, 'revision': revision, 'widgets': widgets}

    def split_legacy_payload(self, revision=0):
        widgets = [
            {
                'id': key,
                'visible': key != 'routines',
                'size': 'compact' if key == 'tasks' else 'full',
            }
            for key in LEGACY_WIDGET_IDS
        ]
        return {'version': 1, 'revision': revision, 'widgets': widgets}

    def test_registry_exposes_required_v2_metadata(self):
        required = {
            'id', 'titleKey', 'category', 'component', 'defaultVisible',
            'defaultOrder', 'defaultSize', 'supportedSizes', 'moduleGate', 'permissionGate',
            'sensitivity', 'refreshPolicy', 'emptyStatePolicy', 'deepLink',
            'settingsSchema',
        }
        self.assertEqual([entry['id'] for entry in TODAY_WIDGET_REGISTRY], list(DEFAULT_WIDGET_ORDER))
        self.assertTrue(all(required <= set(entry) for entry in TODAY_WIDGET_REGISTRY))
        self.assertTrue(all(set(entry['supportedSizes']) <= {'compact', 'medium', 'wide'} for entry in TODAY_WIDGET_REGISTRY))
        self.assertTrue(all(entry['defaultSize'] in entry['supportedSizes'] for entry in TODAY_WIDGET_REGISTRY))
        self.assertEqual(list(DEFAULT_WIDGET_ORDER[:8]), ['situation', 'overview', 'focus', 'timeline', 'week', 'todo', 'quick-actions', 'pinboard'])

    def test_default_roundtrip_is_v2_and_private(self):
        initial = self.client.get(self.url)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.data['version'], TODAY_LAYOUT_VERSION)
        self.assertEqual(initial.data['revision'], 0)
        self.assertEqual([row['id'] for row in initial.data['widgets']], list(DEFAULT_WIDGET_ORDER))
        self.assertIn('todo', DEFAULT_WIDGET_ORDER)
        self.assertNotIn('tasks', DEFAULT_WIDGET_ORDER)
        self.assertNotIn('routines', DEFAULT_WIDGET_ORDER)
        self.assertNotIn('priority', DEFAULT_WIDGET_ORDER)
        self.assertNotIn('next', DEFAULT_WIDGET_ORDER)
        self.assertEqual(
            [row['id'] for row in initial.data['widgets'] if row['visible']],
            ['situation', 'overview', 'focus'],
        )
        self.assertEqual(
            {row['id']: row['size'] for row in initial.data['widgets']},
            {entry['id']: entry['defaultSize'] for entry in TODAY_WIDGET_REGISTRY},
        )
        week = next(row for row in initial.data['widgets'] if row['id'] == 'week')
        self.assertEqual(week['settings'], DEFAULT_WEEK_SETTINGS)
        trip = next(row for row in initial.data['widgets'] if row['id'] == 'trip')
        self.assertEqual(trip['settings'], DEFAULT_TRIP_SETTINGS)
        self.assertFalse(TodayLayout.objects.exists())

        config = deepcopy(initial.data)
        config['widgets'].reverse()
        config['widgets'][0].update(visible=True, size='compact')
        saved = self.client.put(self.url, config, format='json')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.data['revision'], 1)
        self.assertEqual(self.client.get(self.url).data, saved.data)

        self.client.force_authenticate(self.other)
        other_initial = self.client.get(self.url).data
        self.assertEqual(other_initial['revision'], 0)
        self.assertEqual(other_initial['version'], TODAY_LAYOUT_VERSION)
        self.assertEqual(self.client.put(self.url, other_initial, format='json').status_code, 200)
        self.assertEqual(TodayLayout.objects.count(), 2)

    def test_legacy_saved_layout_migrates_core_aliases_todo_and_sizes(self):
        legacy = [
            {
                'id': key,
                'visible': key != 'weather',
                'size': 'compact' if key == 'tasks' else ('square' if key == 'routines' else 'full'),
            }
            for key in LEGACY_WIDGET_IDS
        ]
        TodayLayout.objects.create(family=self.family, user=self.user, widgets=legacy, revision=3)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['version'], TODAY_LAYOUT_VERSION)
        self.assertEqual(response.data['revision'], 3)
        expanded = response.data['widgets']
        ids = [row['id'] for row in expanded]
        self.assertNotIn('tasks', ids)
        self.assertNotIn('routines', ids)
        self.assertNotIn('priority', ids)
        self.assertNotIn('next', ids)
        self.assertIn('focus', ids)
        self.assertIn('timeline', ids)
        todo = next(row for row in expanded if row['id'] == 'todo')
        self.assertEqual(todo, {'id': 'todo', 'visible': True, 'size': 'compact'})
        weather = next(row for row in expanded if row['id'] == 'weather')
        self.assertEqual(weather['size'], 'wide')
        self.assertFalse(weather['visible'])
        self.assertEqual(next(row for row in expanded if row['id'] == 'week')['settings'], DEFAULT_WEEK_SETTINGS)
        self.assertEqual(next(row for row in expanded if row['id'] == 'trip')['size'], 'medium')
        self.assertEqual(next(row for row in expanded if row['id'] == 'pinboard')['size'], 'medium')

        weather_index = ids.index('weather')
        todo_index = ids.index('todo')
        shopping_index = ids.index('shopping')
        self.assertLess(weather_index, todo_index)
        self.assertLess(todo_index, shopping_index)
        focus_index = ids.index('focus')
        trip_index = ids.index('trip')
        self.assertEqual(trip_index, focus_index + 1)
        timeline_index = ids.index('timeline')
        pinboard_index = ids.index('pinboard')
        self.assertEqual(pinboard_index, timeline_index + 1)
        self.assertFalse(next(row for row in expanded if row['id'] == 'inbox')['visible'])
        self.assertFalse(next(row for row in expanded if row['id'] == 'loyalty')['visible'])
        self.assertFalse(next(row for row in expanded if row['id'] == 'overview')['visible'])

        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertEqual(stored.widgets, legacy)

    def test_saved_v2_keeps_personal_order_and_visibility_without_new_default(self):
        custom = [
            {'id': 'situation', 'visible': True, 'size': 'compact'},
            {'id': 'shopping', 'visible': True, 'size': 'compact'},
            {'id': 'focus', 'visible': False, 'size': 'wide'},
            {'id': 'timeline', 'visible': True, 'size': 'wide'},
        ]
        TodayLayout.objects.create(family=self.family, user=self.user, widgets=custom, revision=8)
        response = self.client.get(self.url)
        self.assertEqual(response.data['revision'], 8)
        existing = [row for row in response.data['widgets'] if row['id'] in {entry['id'] for entry in custom}]
        self.assertEqual(existing, custom)
        self.assertFalse(next(row for row in response.data['widgets'] if row['id'] == 'overview')['visible'])
        self.assertEqual(TodayLayout.objects.get().widgets, custom)

    def test_v1_put_is_accepted_and_saved_canonically_as_v2(self):
        response = self.client.put(self.url, self.current_v1_payload(), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['version'], TODAY_LAYOUT_VERSION)
        ids = [row['id'] for row in response.data['widgets']]
        self.assertNotIn('priority', ids)
        self.assertNotIn('next', ids)
        self.assertIn('focus', ids)
        self.assertIn('timeline', ids)
        self.assertEqual(next(row for row in response.data['widgets'] if row['id'] == 'focus')['size'], 'wide')
        self.assertEqual(next(row for row in response.data['widgets'] if row['id'] == 'timeline')['size'], 'wide')
        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertNotIn('priority', [row['id'] for row in stored.widgets])
        self.assertNotIn('next', [row['id'] for row in stored.widgets])

    def test_split_legacy_put_collapses_to_todo_and_core_aliases(self):
        response = self.client.put(self.url, self.split_legacy_payload(), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        ids = [row['id'] for row in response.data['widgets']]
        self.assertNotIn('tasks', ids)
        self.assertNotIn('routines', ids)
        self.assertNotIn('priority', ids)
        self.assertNotIn('next', ids)
        self.assertIn('focus', ids)
        self.assertIn('timeline', ids)
        todo = next(row for row in response.data['widgets'] if row['id'] == 'todo')
        self.assertEqual(todo, {'id': 'todo', 'visible': True, 'size': 'compact'})

    def test_v2_stale_core_aliases_are_accepted_and_canonicalized(self):
        config = deepcopy(self.client.get(self.url).data)
        focus_index = next(index for index, row in enumerate(config['widgets']) if row['id'] == 'focus')
        timeline_index = next(index for index, row in enumerate(config['widgets']) if row['id'] == 'timeline')
        config['widgets'][focus_index]['id'] = 'priority'
        config['widgets'][timeline_index]['id'] = 'next'
        saved = self.client.put(self.url, config, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        ids = [row['id'] for row in saved.data['widgets']]
        self.assertEqual(ids[focus_index], 'focus')
        self.assertEqual(ids[timeline_index], 'timeline')
        stored_ids = [row['id'] for row in TodayLayout.objects.get().widgets]
        self.assertNotIn('priority', stored_ids)
        self.assertNotIn('next', stored_ids)

    def test_v1_square_maps_to_medium_for_supported_widget(self):
        legacy = self.current_v1_payload()
        trip = next(row for row in legacy['widgets'] if row['id'] == 'trip')
        trip['size'] = 'square'
        saved = self.client.put(self.url, legacy, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(next(row for row in saved.data['widgets'] if row['id'] == 'trip')['size'], 'medium')

    def test_unknown_widget_survives_v2_roundtrip_without_domain_data(self):
        config = deepcopy(self.client.get(self.url).data)
        future = {'id': 'future_widget', 'visible': False, 'size': 'medium'}
        config['widgets'].insert(2, future)
        saved = self.client.put(self.url, config, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['widgets'][2], future)
        self.assertEqual(self.client.get(self.url).data['widgets'][2], future)
        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertEqual(stored.widgets[2], future)

        leaked = deepcopy(saved.data)
        next(row for row in leaked['widgets'] if row['id'] == 'future_widget')['settings'] = {'secret': True}
        self.assertEqual(self.client.put(self.url, leaked, format='json').status_code, 400)

    def test_existing_trip_widget_without_settings_normalizes_to_wishes_off(self):
        custom = deepcopy(DEFAULT_WIDGETS)
        trip = next(row for row in custom if row['id'] == 'trip')
        trip.pop('settings')
        TodayLayout.objects.create(family=self.family, user=self.user, widgets=custom, revision=2)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        normalized = next(row for row in response.data['widgets'] if row['id'] == 'trip')
        self.assertEqual(normalized['settings'], DEFAULT_TRIP_SETTINGS)
        self.assertFalse(normalized['settings']['show_wishes'])

    def test_week_and_trip_settings_are_private_and_persisted(self):
        config = self.client.get(self.url).data
        week = next(row for row in config['widgets'] if row['id'] == 'week')
        week['settings'] = {'events': False, 'waste': True, 'holidays': True, 'special': False}
        trip = next(row for row in config['widgets'] if row['id'] == 'trip')
        trip['settings']['show_wishes'] = True
        saved = self.client.put(self.url, config, format='json')
        self.assertEqual(saved.status_code, 200)
        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertEqual(next(row for row in stored.widgets if row['id'] == 'week')['settings'], week['settings'])
        self.assertTrue(next(row for row in stored.widgets if row['id'] == 'trip')['settings']['show_wishes'])

        self.client.force_authenticate(self.other)
        other = self.client.get(self.url).data
        self.assertEqual(next(row for row in other['widgets'] if row['id'] == 'week')['settings'], DEFAULT_WEEK_SETTINGS)
        self.assertEqual(next(row for row in other['widgets'] if row['id'] == 'trip')['settings'], DEFAULT_TRIP_SETTINGS)

    def test_saved_custom_order_is_never_replaced_by_registry_default(self):
        custom = deepcopy(DEFAULT_WIDGETS)
        custom = custom[3:] + custom[:3]
        custom[0].update(visible=False, size='compact')
        TodayLayout.objects.create(family=self.family, user=self.user, widgets=custom, revision=7)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['revision'], 7)
        self.assertEqual(response.data['widgets'], custom)

    def test_quick_actions_introduction_is_hidden_and_preserves_personal_choices(self):
        custom = [row for row in deepcopy(DEFAULT_WIDGETS) if row['id'] != 'quick-actions']
        custom.reverse()
        layout = TodayLayout.objects.create(family=self.family, user=self.user, widgets=custom, revision=7)
        introduced = self.client.get(self.url).data
        quick = next(row for row in introduced['widgets'] if row['id'] == 'quick-actions')
        self.assertEqual(quick, {'id': 'quick-actions', 'visible': False, 'size': 'compact'})
        self.assertEqual([row for row in introduced['widgets'] if row['id'] != 'quick-actions'], custom)
        self.assertEqual(introduced['revision'], 7)
        layout.refresh_from_db()
        self.assertEqual(layout.widgets, custom)
        quick.update(visible=True, size='wide')
        saved = self.client.put(self.url, introduced, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(self.client.get(self.url).data, saved.data)
        invalid = deepcopy(saved.data)
        next(row for row in invalid['widgets'] if row['id'] == 'quick-actions')['size'] = 'medium'
        self.assertEqual(self.client.put(self.url, invalid, format='json').status_code, 400)
        self.assertEqual(self.client.get(self.url).data, saved.data)

    def test_games_registry_introduction_preserves_explicit_hidden_choice(self):
        custom = [row for row in deepcopy(DEFAULT_WIDGETS) if row['id'] != 'games']
        custom.reverse()
        layout = TodayLayout.objects.create(family=self.family, user=self.user, widgets=custom, revision=7)
        introduced = self.client.get(self.url).data
        game = next(row for row in introduced['widgets'] if row['id'] == 'games')
        self.assertEqual(game, {'id': 'games', 'visible': False, 'size': 'medium'})
        self.assertEqual([row for row in introduced['widgets'] if row['id'] != 'games'], custom)
        self.assertEqual(introduced['revision'], 7)
        layout.refresh_from_db()
        self.assertEqual(layout.widgets, custom)
        game['visible'] = False
        game['size'] = 'compact'
        saved = self.client.put(self.url, introduced, format='json')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get(self.url).data, saved.data)
        self.assertEqual(next(row for row in saved.data['widgets'] if row['id'] == 'games'), {'id': 'games', 'visible': False, 'size': 'compact'})

    def test_status_and_pinboard_sizes_roundtrip_without_reordering_saved_choices(self):
        config = deepcopy(self.client.get(self.url).data)
        status = next(row for row in config['widgets'] if row['id'] == 'situation')
        board = next(row for row in config['widgets'] if row['id'] == 'pinboard')
        self.assertEqual(status, {'id': 'situation', 'visible': True, 'size': 'compact'})
        self.assertEqual(board, {'id': 'pinboard', 'visible': False, 'size': 'medium'})
        config['widgets'].reverse()
        status.update(visible=False, size='medium')
        board.update(visible=True, size='wide')
        saved = self.client.put(self.url, config, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data['widgets'], config['widgets'])
        self.assertEqual(self.client.get(self.url).data, saved.data)
        invalid = deepcopy(saved.data)
        next(row for row in invalid['widgets'] if row['id'] == 'situation')['size'] = 'wide'
        self.assertEqual(self.client.put(self.url, invalid, format='json').status_code, 400)
        self.assertEqual(self.client.get(self.url).data, saved.data)

    def test_legacy_status_introduction_keeps_previously_visible_signal_and_stored_rows(self):
        custom = [row for row in deepcopy(DEFAULT_WIDGETS) if row['id'] != 'situation']
        custom.reverse()
        next(row for row in custom if row['id'] == 'pinboard').update(visible=False, size='compact')
        layout = TodayLayout.objects.create(family=self.family, user=self.user, widgets=custom, revision=9)
        first = self.client.get(self.url)
        self.assertEqual(first.data['widgets'][0], {'id': 'situation', 'visible': True, 'size': 'compact'})
        self.assertEqual(first.data['widgets'][1:], custom)
        self.assertEqual(first.data['revision'], 9)
        self.assertEqual(self.client.get(self.url).data, first.data)
        layout.refresh_from_db()
        self.assertEqual(layout.widgets, custom)
        self.assertEqual(layout.revision, 9)
        first.data['widgets'][0].update(visible=False, size='medium')
        saved = self.client.put(self.url, first.data, format='json')
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(self.client.get(self.url).data, saved.data)
        self.assertFalse(saved.data['widgets'][0]['visible'])

    def test_registry_parity_preserves_existing_personal_status_and_pinboard(self):
        custom = deepcopy(DEFAULT_WIDGETS)
        custom.reverse()
        next(row for row in custom if row['id'] == 'situation').update(visible=False, size='medium')
        next(row for row in custom if row['id'] == 'pinboard').update(visible=False, size='compact')
        layout = TodayLayout.objects.create(family=self.family, user=self.user, widgets=custom, revision=9)
        response = self.client.get(self.url)
        self.assertEqual(response.data['widgets'], custom)
        self.assertEqual(response.data['revision'], 9)
        layout.refresh_from_db()
        self.assertEqual(layout.widgets, custom)
        self.assertEqual(layout.revision, 9)

    def test_v2_medium_is_allowed_only_for_supported_widgets(self):
        valid = deepcopy(self.client.get(self.url).data)
        for key in ('trip', 'todo', 'week'):
            next(row for row in valid['widgets'] if row['id'] == key)['size'] = 'medium'
        saved = self.client.put(self.url, valid, format='json')
        self.assertEqual(saved.status_code, 200)
        for key in ('trip', 'todo', 'week'):
            self.assertEqual(next(row for row in saved.data['widgets'] if row['id'] == key)['size'], 'medium')

        invalid_focus = deepcopy(saved.data)
        next(row for row in invalid_focus['widgets'] if row['id'] == 'focus')['size'] = 'medium'
        self.assertEqual(self.client.put(self.url, invalid_focus, format='json').status_code, 400)

    def test_stale_writes_do_not_overwrite(self):
        initial = self.client.get(self.url).data
        self.assertEqual(self.client.put(self.url, initial, format='json').status_code, 200)
        initial['widgets'][0]['visible'] = False
        conflict = self.client.put(self.url, initial, format='json')
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data['current']['revision'], 1)
        self.assertTrue(TodayLayout.objects.get().widgets[0]['visible'])

    def test_invalid_payloads_and_domain_fields_are_rejected(self):
        valid = deepcopy(self.client.get(self.url).data)
        invalid = []
        for field, value in [('version', 3), ('version', True), ('revision', -1), ('revision', True), ('widgets', [])]:
            item = deepcopy(valid)
            item[field] = value
            invalid.append(item)
        for field, value in [('id', 'Private Data'), ('visible', 'true'), ('size', 'giant'), ('extra', 1)]:
            item = deepcopy(valid)
            item['widgets'][0][field] = value
            invalid.append(item)
        week_index = next(index for index, row in enumerate(valid['widgets']) if row['id'] == 'week')
        item = deepcopy(valid)
        item['widgets'][week_index]['settings']['events'] = 'yes'
        invalid.append(item)
        item = deepcopy(valid)
        item['widgets'][week_index]['settings']['secret'] = True
        invalid.append(item)
        trip_index = next(index for index, row in enumerate(valid['widgets']) if row['id'] == 'trip')
        item = deepcopy(valid)
        item['widgets'][trip_index]['settings']['show_wishes'] = 'yes'
        invalid.append(item)
        item = deepcopy(valid)
        item['widgets'][trip_index]['settings']['secret'] = True
        invalid.append(item)
        focus_index = next(index for index, row in enumerate(valid['widgets']) if row['id'] == 'focus')
        item = deepcopy(valid)
        item['widgets'][focus_index]['settings'] = deepcopy(DEFAULT_WEEK_SETTINGS)
        invalid.append(item)
        item = deepcopy(valid)
        item['widgets'][1] = item['widgets'][0]
        invalid.append(item)
        item = deepcopy(valid)
        item['user'] = self.other.id
        invalid.append(item)

        for item in invalid:
            with self.subTest(item=item):
                self.assertEqual(self.client.put(self.url, item, format='json').status_code, 400)
        self.assertFalse(TodayLayout.objects.exists())

    def test_family_isolation_and_auth(self):
        self.assertEqual(self.client.get(f'/api/today-layout/?family={self.foreign.id}').status_code, 404)
        self.assertEqual(self.client.get('/api/today-layout/?family=invalid').status_code, 404)
        self.assertEqual(self.client.get('/api/today-layout/').status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, (401, 403))
