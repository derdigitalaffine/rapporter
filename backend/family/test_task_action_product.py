from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Family, Membership, Task, TaskList, Routine
from .unified_action_models import Action, ActionCompletion


class TaskActionProductTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('action-product')
        self.family = Family.objects.create(name='Product', slug='product')
        self.member = Membership.objects.create(user=self.user, family=self.family, role='owner')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.schedule = {'mode': 'static', 'recurrence': {'frequency': 'weekly', 'weekdays': ['MO']}}

    def create(self, **data):
        return self.client.post('/api/tasks/', {'family': str(self.family.id), 'title': 'Same action', **data}, format='json')

    def test_create_and_edit_share_atomic_task_action_schedule(self):
        response = self.create(action_schedule=self.schedule)
        self.assertEqual(response.status_code, 201, response.data)
        task = Task.objects.get(pk=response.data['id'])
        self.assertEqual(Action.objects.count(), 1)
        self.assertEqual(task.unified_action.schedule['recurrence']['weekdays'], ['MO'])
        self.assertEqual(response.data['action_schedule'], task.unified_action.schedule)
        response = self.client.patch(f'/api/tasks/{task.id}/', {'title': 'Changed', 'action_schedule': {}}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        task.refresh_from_db()
        self.assertEqual(task.unified_action.title, 'Changed')
        self.assertEqual(task.unified_action.schedule, {})
        self.assertEqual(response.data['action_schedule'], {})

    def test_invalid_schedule_creates_neither_task_nor_action(self):
        for value in [[], ['wrong'], 'weekly', {'mode': 'static', 'recurrence': {'frequency': 'invalid'}}]:
            response = self.create(action_schedule=value)
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Task.objects.count(), 0)
        self.assertEqual(Action.objects.count(), 0)

    def test_invalid_update_preserves_task_and_schedule(self):
        created = self.create(action_schedule=self.schedule).data
        response = self.client.patch(f"/api/tasks/{created['id']}/", {'title': 'Must not change', 'action_schedule': {'mode': 'invalid'}}, format='json')
        self.assertEqual(response.status_code, 400)
        task = Task.objects.get(pk=created['id'])
        self.assertEqual(task.title, 'Same action')
        self.assertEqual(task.unified_action.schedule['mode'], 'static')

    def test_source_permissions_and_suspended_family_are_preserved(self):
        foreign = Family.objects.create(name='Foreign', slug='foreign')
        foreign_list = TaskList.objects.create(family=foreign, name='Private')
        other = get_user_model().objects.create_user('foreign-assignee')
        for data in [{'task_list': str(foreign_list.id)}, {'assignee': other.id}, {'family': str(foreign.id)}]:
            self.assertIn(self.create(**data).status_code, [400, 403])
        self.family.status = 'suspended'
        self.family.save()
        self.assertEqual(self.create(action_schedule=self.schedule).status_code, 403)
        self.assertEqual(Task.objects.count(), 0)

    def test_capture_new_task_is_same_object_retry_safe_and_undoable(self):
        path = f'/api/actions/capture/?family={self.family.id}'
        body = {'title': 'Already done', 'create_new': True, 'create_kind': 'task', 'request_id': str(uuid4())}
        first = self.client.post(path, body, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        retry = self.client.post(path, body, format='json')
        self.assertEqual(retry.data['id'], first.data['id'])
        self.assertEqual(retry.data['action_id'], first.data['action_id'])
        self.assertEqual(self.client.post(path, {**body, 'title': 'Different work'}, format='json').status_code, 400)
        task = Task.objects.get(title='Already done')
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(Routine.objects.count(), 0)
        self.assertEqual(Action.objects.count(), 1)
        self.assertEqual(ActionCompletion.objects.count(), 1)
        self.assertEqual(first.data['action_id'], f'task:{task.id}')
        undone = self.client.post('/api/actions/execute/', {'action_id': first.data['action_id'], 'operation': 'undo', 'completion_id': first.data['id'], 'request_id': str(uuid4())}, format='json')
        self.assertEqual(undone.status_code, 200, undone.data)
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)
        self.client.post(path, body, format='json')
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)

    def test_quarterly_task_completion_does_not_reuse_previous_cycle(self):
        response = self.create(action_schedule={'mode': 'static', 'recurrence': {'frequency': 'quarterly', 'interval': 1}})
        self.assertEqual(response.status_code, 201, response.data)
        task = Task.objects.get(pk=response.data['id'])
        ids = []
        for _ in range(2):
            completed = self.client.post('/api/actions/execute/', {'action_id': f'task:{task.id}', 'request_id': str(uuid4())}, format='json')
            self.assertEqual(completed.status_code, 200, completed.data)
            ids.append(completed.data['id'])
        self.assertNotEqual(*ids)
        self.assertEqual(task.unified_action.completions.count(), 2)

    def test_offline_sync_uses_same_atomic_serializer_and_retry_receipt(self):
        entity_id = str(uuid4())
        mutation = {'mutation_id': str(uuid4()), 'entity_type': 'task', 'entity_id': entity_id, 'operation': 'create', 'base_version': None, 'data': {'title': 'Offline recurrence', 'action_schedule': self.schedule}}
        data = {'protocol_version': 1, 'family_id': str(self.family.id), 'cursor': None, 'mutations': [mutation]}
        first = self.client.post('/api/sync/', data, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['mutation_results'][0]['status'], 'applied', first.data)
        second = self.client.post('/api/sync/', data, format='json')
        self.assertEqual(second.data['mutation_results'][0]['status'], 'already_applied', second.data)
        task = Task.objects.get(pk=entity_id)
        self.assertEqual(task.unified_action.schedule['recurrence']['weekdays'], ['MO'])
        self.assertEqual(len(first.data['snapshot']['tasks']), 1)
        self.assertEqual(first.data['snapshot']['tasks'][0]['action_schedule'], task.unified_action.schedule)
