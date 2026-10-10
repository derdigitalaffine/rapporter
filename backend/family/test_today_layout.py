from copy import deepcopy

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, TodayLayout
from .today_layout_views import DEFAULT_WIDGET_ORDER, DEFAULT_WIDGETS, LEGACY_WIDGET_IDS


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
        self.assertTrue(all(row['visible'] for row in initial.data['widgets']))
        self.assertFalse(TodayLayout.objects.exists())
        config = deepcopy(initial.data); config['widgets'].reverse(); config['widgets'][0].update(visible=False, size='compact')
        saved = self.client.put(self.url, config, format='json')
        self.assertEqual(saved.status_code, 200); self.assertEqual(saved.data['revision'], 1)
        self.assertEqual(self.client.get(self.url).data, saved.data)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).data['revision'], 0)
        self.assertEqual(self.client.put(self.url, initial.data, format='json').status_code, 200)
        self.assertEqual(TodayLayout.objects.count(), 2)

    def test_legacy_saved_layout_restores_trip_without_changing_existing_settings(self):
        legacy = [
            {'id': key, 'visible': key != 'weather', 'size': 'compact' if key == 'tasks' else 'full'}
            for key in LEGACY_WIDGET_IDS
        ]
        TodayLayout.objects.create(family=self.family, user=self.user, widgets=legacy, revision=3)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['revision'], 3)
        expanded = response.data['widgets']
        self.assertEqual([row for row in expanded if row['id'] in LEGACY_WIDGET_IDS], legacy)
        trip_index = next(index for index, row in enumerate(expanded) if row['id'] == 'trip')
        priority_index = next(index for index, row in enumerate(expanded) if row['id'] == 'priority')
        self.assertEqual(trip_index, priority_index + 1)
        self.assertEqual(expanded[trip_index], {'id': 'trip', 'visible': True, 'size': 'full'})
        self.assertEqual(expanded[-2:], [
            {'id': 'loyalty', 'visible': False, 'size': 'full'},
            {'id': 'inbox', 'visible': False, 'size': 'full'},
        ])
        stored = TodayLayout.objects.get(family=self.family, user=self.user)
        self.assertEqual(stored.widgets, legacy)

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
        invalid['revision'] = saved.data['revision']
        task = next(row for row in invalid['widgets'] if row['id'] == 'tasks')
        task['size'] = 'square'
        self.assertEqual(self.client.put(self.url, invalid, format='json').status_code, 400)

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