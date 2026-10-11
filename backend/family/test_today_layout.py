from copy import deepcopy

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, TodayLayout
from .today_layout_views import (
    DEFAULT_TRIP_SETTINGS,
    DEFAULT_WEEK_SETTINGS,
    DEFAULT_WIDGET_ORDER,
    DEFAULT_WIDGETS,
    LEGACY_WIDGET_IDS,
)


class TodayLayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='widget-owner')
        self.other = get_user_model().objects.create_user(username='widget-other')
        self.family = Family.objects.create(name='Widgets', slug='widgets')
        self.foreign = Family.objects.create(name='Foreign', slug='widgets-foreign')
        Membership.objects.create(user=self.user, family=self.family, role='owner')
        Membership.objects.create(user=self.other, family=self.family, role='child')
        Membership.objects.create(user=self.other, family=self.foreign, role='owner')
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.url = f'/api/today-layout/?family={self.family.id}'

    def test_default_roundtrip_private(self):
        initial = self.client.get(self.url)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.data['revision'], 0)
        self.assertEqual([row['id'] for row in initial.data['widgets']], list(DEFAULT_WIDGET_ORDER))
        self.assertIn('todo', DEFAULT_WIDGET_ORDER)
        self.assertNotIn('tasks', DEFAULT_WIDGET_ORDER)
        self.assertNotIn('routines', DEFAULT_WIDGET_ORDER)
        self.assertTrue(all(row['visible'] for row in initial.data['widgets']))
        self.assertEqual(initial.data['widgets'][0]['settings'], DEFAULT_WEEK_SETTINGS)
        trip = next(row for row in initial.data['widgets'] if row['id'] == 'trip')
        self.assertEqual(trip['settings'], DEFAULT_TRIP_SETTINGS)
        self.assertFalse(TodayLayout.objects.exists())
        config = deepcopy(initial.data); config['widgets'].reverse(); config['widgets'][0].update(visible=False, size='compact')
        saved = self.client.put(self.url, config, format='json')
        self.assertEqual(saved.status_code, 200); self.assertEqual(saved.data['revision'], 1)
        self.assertEqual(self.client.get(self.url).data, saved.data)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).data['revision'], 0)
        self.assertEqual(self.client.put(self.url, initial.data, format='json').status_code, 200)
        self.assertEqual(TodayLayout.objects.count(), 2)

    def test_legacy_saved_layout_collapses_tasks_and_routines_into_todo(self):
        legacy = [
            {'id': key, 'visible': key != 'weather', 'size': 'compact' if key == 'tasks' else ('square' if key == 'routines' else 'full')}
            for key in LEGACY_WIDGET_IDS
        ]
        TodayLayout.objects.create(family=self.family, user=self.user, widgets=legacy, revision=3)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['revision'], 3)
        expanded = response.data['widgets']
        ids = [row['id'] for row in expanded]
        self.assertNotIn('tasks', ids)
        self.assertNotIn('routines', ids)
        todo = next(row for row in expanded if row['id'] == 'todo')
        self.assertEqual(todo, {'id': 'todo', 'visible': True, 'size': 'compact'})
        weather_index = next(index for index, row in enumerate(expanded) if row['id'] == 'weather')
        todo_index = next(index for index, row in enumerate(expanded) if row['id'] == 'todo')
        shopping_index = next(index for index, row in enumerate(expanded) if row['id'] == 'shopping')
        self.assertLess(weather_index, todo_index)
        self.assertLess(todo_index, shopping_index)
        self.assertEqual(expanded[0], {'id': 'week', 'visible': True, 'size': 'full', 'settings': DEFAULT_WEEK_SETTINGS})
        priority_index = next(index for index, row in enumerate(expanded) if row['id'] == 'priority')
        trip_index = next(index for index, row in enumerate(expanded) if row['id'] == 'trip')
        self.assertEqual(trip_index, priority_index + 1)
        next_index = next(index for index, row in enumerate(expanded) if row['id'] == 'next')
        pinboard_index = next(index for index, row in enumerate(expanded) if row['id'] == 'pinboard')
        self.assertEqual(pinboard_index, next_index + 1)
        self.assertEqual(expanded[-2:], [
            {'id': 'loyalty', 'visible': False, 'size': 'full'},
            {'id': 'inbox', 'visible': False, 'size': 'full'},
        ])
        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertEqual(stored.widgets, legacy)

    def test_stale_client_put_is_accepted_and_saved_canonically(self):
        legacy = [
            {'id': key, 'visible': key != 'routines', 'size': 'compact' if key == 'tasks' else 'full'}
            for key in LEGACY_WIDGET_IDS
        ]
        response = self.client.put(self.url, {'version': 1, 'revision': 0, 'widgets': legacy}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('tasks', [row['id'] for row in response.data['widgets']])
        self.assertNotIn('routines', [row['id'] for row in response.data['widgets']])
        todo = next(row for row in response.data['widgets'] if row['id'] == 'todo')
        self.assertEqual(todo, {'id': 'todo', 'visible': True, 'size': 'compact'})
        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertIn('todo', [row['id'] for row in stored.widgets])
        self.assertNotIn('tasks', [row['id'] for row in stored.widgets])
        self.assertNotIn('routines', [row['id'] for row in stored.widgets])

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

    def test_week_settings_are_private_and_persisted(self):
        config = self.client.get(self.url).data
        week = next(row for row in config['widgets'] if row['id'] == 'week')
        week['settings'] = {'events': False, 'waste': True, 'holidays': True, 'special': False}
        saved = self.client.put(self.url, config, format='json')
        self.assertEqual(saved.status_code, 200)
        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertEqual(next(row for row in stored.widgets if row['id'] == 'week')['settings'], week['settings'])
        self.client.force_authenticate(self.other)
        other_week = next(row for row in self.client.get(self.url).data['widgets'] if row['id'] == 'week')
        self.assertEqual(other_week['settings'], DEFAULT_WEEK_SETTINGS)

    def test_trip_wish_setting_is_private_and_persisted(self):
        config = self.client.get(self.url).data
        trip = next(row for row in config['widgets'] if row['id'] == 'trip')
        trip['settings']['show_wishes'] = True
        saved = self.client.put(self.url, config, format='json')
        self.assertEqual(saved.status_code, 200)
        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertTrue(next(row for row in stored.widgets if row['id'] == 'trip')['settings']['show_wishes'])
        self.client.force_authenticate(self.other)
        other_trip = next(row for row in self.client.get(self.url).data['widgets'] if row['id'] == 'trip')
        self.assertEqual(other_trip['settings'], DEFAULT_TRIP_SETTINGS)

    def test_saved_custom_order_is_never_replaced_by_new_reference_default(self):
        custom = deepcopy(DEFAULT_WIDGETS)
        custom = custom[3:] + custom[:3]
        custom[0].update(visible=False, size='compact')
        TodayLayout.objects.create(family=self.family, user=self.user, widgets=custom, revision=7)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['revision'], 7)
        self.assertEqual(response.data['widgets'], custom)

    def test_square_size_is_allowed_only_for_supported_widgets(self):
        valid = {'version': 1, 'revision': 0, 'widgets': deepcopy(DEFAULT_WIDGETS)}
        trip = next(row for row in valid['widgets'] if row['id'] == 'trip')
        trip['size'] = 'square'
        saved = self.client.put(self.url, valid, format='json')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(next(row for row in saved.data['widgets'] if row['id'] == 'trip')['size'], 'square')

        invalid = deepcopy(saved.data)
        todo = next(row for row in invalid['widgets'] if row['id'] == 'todo')
        todo['size'] = 'square'
        self.assertEqual(self.client.put(self.url, invalid, format='json').status_code, 400)

        invalid_week = deepcopy(saved.data)
        week = next(row for row in invalid_week['widgets'] if row['id'] == 'week')
        week['size'] = 'square'
        self.assertEqual(self.client.put(self.url, invalid_week, format='json').status_code, 400)

    def test_stale_writes_do_not_overwrite(self):
        initial = self.client.get(self.url).data
        self.assertEqual(self.client.put(self.url, initial, format='json').status_code, 200)
        initial['widgets'][0]['visible'] = False
        conflict = self.client.put(self.url, initial, format='json')
        self.assertEqual(conflict.status_code, 409); self.assertEqual(conflict.data['current']['revision'], 1)
        self.assertTrue(TodayLayout.objects.get().widgets[0]['visible'])

    def test_invalid_payloads(self):
        valid = {'version': 1, 'revision': 0, 'widgets': deepcopy(DEFAULT_WIDGETS)}; invalid = []
        for field, value in [('version', True), ('revision', -1), ('revision', True), ('widgets', [])]:
            item = deepcopy(valid); item[field] = value; invalid.append(item)
        for field, value in [('id', 'private-data'), ('visible', 'true'), ('size', 'giant'), ('extra', 1)]:
            item = deepcopy(valid); item['widgets'][0][field] = value; invalid.append(item)
        item = deepcopy(valid); item['widgets'][0]['settings']['events'] = 'yes'; invalid.append(item)
        item = deepcopy(valid); item['widgets'][0]['settings']['secret'] = True; invalid.append(item)
        trip_index = next(index for index, row in enumerate(valid['widgets']) if row['id'] == 'trip')
        item = deepcopy(valid); item['widgets'][trip_index]['settings']['show_wishes'] = 'yes'; invalid.append(item)
        item = deepcopy(valid); item['widgets'][trip_index]['settings']['secret'] = True; invalid.append(item)
        priority_index = next(index for index, row in enumerate(valid['widgets']) if row['id'] == 'priority')
        item = deepcopy(valid); item['widgets'][priority_index]['settings'] = deepcopy(DEFAULT_WEEK_SETTINGS); invalid.append(item)
        item = deepcopy(valid); item['widgets'][1] = item['widgets'][0]; invalid.append(item)
        item = deepcopy(valid); item['user'] = self.other.id; invalid.append(item)
        for item in invalid:
            with self.subTest(item=item): self.assertEqual(self.client.put(self.url, item, format='json').status_code, 400)
        self.assertFalse(TodayLayout.objects.exists())

    def test_family_isolation_and_auth(self):
        self.assertEqual(self.client.get(f'/api/today-layout/?family={self.foreign.id}').status_code, 404)
        self.assertEqual(self.client.get('/api/today-layout/?family=invalid').status_code, 404)
        self.assertEqual(self.client.get('/api/today-layout/').status_code, 404)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, (401, 403))