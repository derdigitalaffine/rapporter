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
        widgets = deepcopy(DEFAULT_WIDGETS)
        for row in widgets:
            row['size'] = 'full'
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
            'defaultOrder', 'supportedSizes', 'moduleGate', 'permissionGate',
            'sensitivity', 'refreshPolicy', 'emptyStatePolicy', 'deepLink',
            'settingsSchema',
        }
        self.assertEqual([entry['id'] for entry in TODAY_WIDGET_REGISTRY], list(DEFAULT_WIDGET_ORDER))
        self.assertTrue(all(required <= set(entry) for entry in TODAY_WIDGET_REGISTRY))
        self.assertTrue(all(set(entry['supportedSizes']) <= {'compact', 'medium', 'wide'} for entry in TODAY_WIDGET_REGISTRY))

    def test_default_roundtrip_is_v2_and_private(self):
        initial = self.client.get(self.url)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.data['version'], TODAY_LAYOUT_VERSION)
        self.assertEqual(initial.data['revision'], 0)
        self.assertEqual([row['id'] for row in initial.data['widgets']], list(DEFAULT_WIDGET_ORDER))
        self.assertIn('todo', DEFAULT_WIDGET_ORDER)
        self.assertNotIn('tasks', DEFAULT_WIDGET_ORDER)
        self.assertNotIn('routines', DEFAULT_WIDGET_ORDER)
        self.assertTrue(all(row['visible'] for row in initial.data['widgets']))
        self.assertTrue(all(row['size'] == 'wide' for row in initial.data['widgets']))
        self.assertEqual(initial.data['widgets'][0]['settings'], DEFAULT_WEEK_SETTINGS)
        trip = next(row for row in initial.data['widgets'] if row['id'] == 'trip')
        self.assertEqual(trip['settings'], DEFAULT_TRIP_SETTINGS)
        self.assertFalse(TodayLayout.objects.exists())

        config = deepcopy(initial.data)
        config['widgets'].reverse()
        config['widgets'][0].update(visible=False, size='compact')
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

    def test_legacy_saved_layout_collapses_tasks_and_routines_and_maps_sizes(self):
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
        todo = next(row for row in expanded if row['id'] == 'todo')
        self.assertEqual(todo, {'id': 'todo', 'visible': True, 'size': 'compact'})
        weather = next(row for row in expanded if row['id'] == 'weather')
        self.assertEqual(weather['size'], 'wide')
        self.assertFalse(weather['visible'])
        self.assertEqual(expanded[0], {'id': 'week', 'visible': True, 'size': 'wide', 'settings': DEFAULT_WEEK_SETTINGS})

        weather_index = next(index for index, row in enumerate(expanded) if row['id'] == 'weather')
        todo_index = next(index for index, row in enumerate(expanded) if row['id'] == 'todo')
        shopping_index = next(index for index, row in enumerate(expanded) if row['id'] == 'shopping')
        self.assertLess(weather_index, todo_index)
        self.assertLess(todo_index, shopping_index)
        priority_index = next(index for index, row in enumerate(expanded) if row['id'] == 'priority')
        trip_index = next(index for index, row in enumerate(expanded) if row['id'] == 'trip')
        self.assertEqual(trip_index, priority_index + 1)
        next_index = next(index for index, row in enumerate(expanded) if row['id'] == 'next')
        pinboard_index = next(index for index, row in enumerate(expanded) if row['id'] == 'pinboard')
        self.assertEqual(pinboard_index, next_index + 1)
        self.assertFalse(next(row for row in expanded if row['id'] == 'inbox')['visible'])
        self.assertFalse(next(row for row in expanded if row['id'] == 'loyalty')['visible'])

        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertEqual(stored.widgets, legacy)

    def test_v1_put_is_accepted_and_saved_canonically_as_v2(self):
        response = self.client.put(self.url, self.current_v1_payload(), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['version'], TODAY_LAYOUT_VERSION)
        self.assertTrue(all(row['size'] == 'wide' for row in response.data['widgets']))
        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertTrue(all(row['size'] == 'wide' for row in stored.widgets))

    def test_split_legacy_put_collapses_to_todo(self):
        response = self.client.put(self.url, self.split_legacy_payload(), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        ids = [row['id'] for row in response.data['widgets']]
        self.assertNotIn('tasks', ids)
        self.assertNotIn('routines', ids)
        todo = next(row for row in response.data['widgets'] if row['id'] == 'todo')
        self.assertEqual(todo, {'id': 'todo', 'visible': True, 'size': 'compact'})

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

    def test_v2_medium_is_allowed_only_for_supported_widgets(self):
        valid = deepcopy(self.client.get(self.url).data)
        trip = next(row for row in valid['widgets'] if row['id'] == 'trip')
        trip['size'] = 'medium'
        saved = self.client.put(self.url, valid, format='json')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(next(row for row in saved.data['widgets'] if row['id'] == 'trip')['size'], 'medium')

        invalid_todo = deepcopy(saved.data)
        next(row for row in invalid_todo['widgets'] if row['id'] == 'todo')['size'] = 'medium'
        self.assertEqual(self.client.put(self.url, invalid_todo, format='json').status_code, 400)

        invalid_week = deepcopy(saved.data)
        next(row for row in invalid_week['widgets'] if row['id'] == 'week')['size'] = 'medium'
        self.assertEqual(self.client.put(self.url, invalid_week, format='json').status_code, 400)

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
        item = deepcopy(valid)
        item['widgets'][0]['settings']['events'] = 'yes'
        invalid.append(item)
        item = deepcopy(valid)
        item['widgets'][0]['settings']['secret'] = True
        invalid.append(item)
        trip_index = next(index for index, row in enumerate(valid['widgets']) if row['id'] == 'trip')
        item = deepcopy(valid)
        item['widgets'][trip_index]['settings']['show_wishes'] = 'yes'
        invalid.append(item)
        item = deepcopy(valid)
        item['widgets'][trip_index]['settings']['secret'] = True
        invalid.append(item)
        priority_index = next(index for index, row in enumerate(valid['widgets']) if row['id'] == 'priority')
        item = deepcopy(valid)
        item['widgets'][priority_index]['settings'] = deepcopy(DEFAULT_WEEK_SETTINGS)
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
