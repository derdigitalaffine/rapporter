from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, Membership, Task, TaskList, TaskStatusEvent, TaskWorkflowColumn
from .task_workflow import configure_workflow


class WorkflowTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='workflow-owner')
        self.family=Family.objects.create(name='Workflow',slug='workflow')
        Membership.objects.create(family=self.family,user=self.user,role='owner')
        self.list=TaskList.objects.create(family=self.family,name='Umzug')
        self.client=APIClient();self.client.force_authenticate(self.user)

    def activate(self):
        self.list=configure_workflow(self.list,True)
        self.columns={row.kind:row for row in self.list.workflow_columns.all()}

    def task(self,**kwargs):
        return Task.objects.create(family=self.family,task_list=self.list,title='Kisten packen',created_by=self.user,**kwargs)

    def test_simple_list_has_no_workflow_or_history(self):
        task=self.task()
        self.assertIsNone(task.workflow_column)
        self.assertFalse(self.list.workflow_enabled)
        self.assertFalse(TaskStatusEvent.objects.exists())

    def test_activation_maps_open_and_completed_without_data_loss(self):
        open_task=self.task(notes='Bücher',priority='high')
        done_task=self.task(completed_at=timezone.now())
        self.activate()
        open_task.refresh_from_db();done_task.refresh_from_db()
        self.assertEqual(open_task.workflow_column,self.columns['open'])
        self.assertEqual(done_task.workflow_column,self.columns['done'])
        self.assertEqual(open_task.notes,'Bücher')
        configure_workflow(self.list,False)
        done_task.refresh_from_db()
        self.assertIsNotNone(done_task.completed_at)
        self.assertEqual(Task.objects.count(),2)

    def test_move_complete_reopen_preserves_metadata_and_records_once(self):
        self.activate();task=self.task(notes='Bücher',priority='high',assignee=self.user)
        for kind in ['active','done']:
            response=self.client.post(f'/api/tasks/{task.id}/move/',{'column_id':str(self.columns[kind].id)},format='json')
            self.assertEqual(response.status_code,200,response.data)
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(task.notes,'Bücher');self.assertEqual(task.assignee,self.user)
        self.client.post(f'/api/tasks/{task.id}/toggle/')
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)
        self.assertEqual(task.workflow_column,self.columns['active'])
        before=task.status_events.count()
        self.client.post(f'/api/tasks/{task.id}/move/',{'column_id':str(self.columns['active'].id)},format='json')
        self.assertEqual(task.status_events.count(),before)
        history=self.client.get(f'/api/tasks/{task.id}/status-history/')
        self.assertEqual(history.status_code,200)
        self.assertEqual(history.data['count'],4)

    def test_patch_completion_and_quick_add_use_same_invariant(self):
        self.activate()
        response=self.client.post('/api/smart/tasks/quick-add/',{'family':str(self.family.id),'task_list':str(self.list.id),'title':'Quick'},format='json')
        self.assertEqual(response.status_code,201)
        task=Task.objects.get(title='Quick')
        self.assertEqual(task.workflow_column,self.columns['open'])
        response=self.client.patch(f'/api/tasks/{task.id}/',{'completed_at':timezone.now().isoformat()},format='json')
        self.assertEqual(response.status_code,200,response.data)
        task.refresh_from_db();self.assertEqual(task.workflow_column,self.columns['done'])

    def test_reorder_is_persistent_and_does_not_create_status_event(self):
        self.activate();first=self.task();second=self.task();third=self.task()
        before=third.status_events.count()
        response=self.client.post(f'/api/tasks/{third.id}/move/',{'column_id':str(self.columns['open'].id),'before_task_id':str(second.id)},format='json')
        self.assertEqual(response.status_code,200)
        ids=list(Task.objects.order_by('workflow_position').values_list('id',flat=True))
        self.assertEqual(ids,[first.id,third.id,second.id]);self.assertEqual(third.status_events.count(),before)

    def test_foreign_column_or_task_and_invalid_before_are_rejected(self):
        self.activate();task=self.task()
        other=Family.objects.create(name='Other',slug='workflow-other')
        other_list=configure_workflow(TaskList.objects.create(family=other,name='Other'),True)
        column=other_list.workflow_columns.first()
        response=self.client.post(f'/api/tasks/{task.id}/move/',{'column_id':str(column.id)},format='json')
        self.assertEqual(response.status_code,400)
        response=self.client.patch(f'/api/tasks/{task.id}/',{'workflow_column':str(column.id)},format='json')
        self.assertEqual(response.status_code,400)
        response=self.client.post(f'/api/tasks/{task.id}/move/',{'column_id':str(self.columns['open'].id),'before_task_id':str(task.id)},format='json')
        self.assertEqual(response.status_code,400)

    def test_column_rules_and_configuration_permissions(self):
        self.activate();self.task()
        response=self.client.delete(f"/api/task-workflow-columns/{self.columns['open'].id}/")
        self.assertEqual(response.status_code,400)
        response=self.client.patch(f"/api/task-workflow-columns/{self.columns['done'].id}/",{'archived':True},format='json')
        self.assertEqual(response.status_code,400)
        response=self.client.post(f'/api/task-lists/{self.list.id}/workflow-columns/',{'name':'Wartet','kind':'waiting'},format='json')
        self.assertEqual(response.status_code,201,response.data)
        teen=get_user_model().objects.create_user(username='workflow-teen')
        Membership.objects.create(family=self.family,user=teen,role='teen');self.client.force_authenticate(teen)
        response=self.client.patch(f'/api/task-lists/{self.list.id}/',{'workflow_enabled':False},format='json')
        self.assertEqual(response.status_code,403)
        response=self.client.patch(f"/api/task-workflow-columns/{self.columns['active'].id}/",{'name':'Neu'},format='json')
        self.assertEqual(response.status_code,403)
