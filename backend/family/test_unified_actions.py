from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import uuid4
from django.test import TestCase, SimpleTestCase
from django.contrib.auth import get_user_model
from django.core.management import call_command
from io import StringIO
from rest_framework.test import APIClient
from .models import Family, Membership, Task, TaskList, Routine, RoutineLog
from .unified_action_models import Action, ActionCompletion
from .action_schedule import normalize_schedule, predict, parse_schedule
from .task_workflow import configure_workflow

UTC = dt_timezone.utc

class UnifiedCompletionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='unified-actor')
        self.other = get_user_model().objects.create_user(username='unified-assignee')
        self.family = Family.objects.create(name='Unified', slug='unified')
        Membership.objects.create(user=self.user, family=self.family, role='owner')
        Membership.objects.create(user=self.other, family=self.family, role='adult')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.task = Task.objects.create(family=self.family, title='Task', assignee=self.other, created_by=self.user)
        self.routine = Routine.objects.create(family=self.family, name='Routine')
    def execute(self, obj, **kwargs):
        kind = 'task' if isinstance(obj, Task) else 'routine'
        return self.client.post('/api/actions/execute/', {'action_id': f'{kind}:{obj.id}', 'request_id': str(uuid4()), **kwargs}, format='json')
    def test_task_retry_actor_duration_and_undo(self):
        key = str(uuid4())
        first = self.execute(self.task, request_id=key, duration_minutes=15)
        self.assertEqual(first.status_code, 200, first.data)
        retry = self.execute(self.task, request_id=key, duration_minutes=15)
        self.assertEqual(retry.data['id'], first.data['id'])
        self.task.refresh_from_db()
        self.assertIsNotNone(self.task.completed_at)
        completion = ActionCompletion.objects.get(pk=first.data['id'])
        self.assertEqual(completion.actor_id, self.user.id)
        self.assertEqual(completion.duration_minutes, 15)
        self.assertEqual(self.task.assignee_id, self.other.id)
        self.assertEqual(self.execute(self.task, operation='undo', completion_id=first.data['id']).status_code, 200)
        self.execute(self.task, request_id=key)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.completed_at)
        self.assertEqual(self.task.unified_action.completions.count(), 1)
    def test_routine_retry_and_legacy_history(self):
        key = str(uuid4())
        result = self.execute(self.routine, request_id=key, duration_minutes=10)
        self.assertEqual(result.status_code, 200, result.data)
        self.execute(self.routine, request_id=key)
        self.assertEqual(self.routine.logs.count(), 1)
        self.assertEqual(self.execute(self.routine, operation='undo', completion_id=result.data['id']).status_code, 200)
        self.assertEqual(self.routine.logs.count(), 0)
        self.assertIsNotNone(ActionCompletion.objects.get(pk=result.data['id']).undone_at)
    def test_foreign_hidden_suspended_and_bad_input(self):
        foreign = Family.objects.create(name='Foreign', slug='foreign')
        task = Task.objects.create(family=foreign, title='Secret')
        self.assertEqual(self.execute(task).status_code, 404)
        self.task.hidden_from_user = self.user
        self.task.save()
        self.assertEqual(self.execute(self.task).status_code, 404)
        self.assertEqual(self.execute(self.routine, duration_minutes=True).status_code, 400)
        self.assertEqual(self.execute(self.routine, request_id='bad').status_code, 400)
        self.family.status = 'suspended'
        self.family.save()
        self.assertEqual(self.execute(self.routine).status_code, 404)
    def test_workflow_terminal_and_reopen_preserved(self):
        task_list = TaskList.objects.create(family=self.family, name='Flow')
        configure_workflow(task_list, True)
        self.task.task_list = task_list
        self.task.save()
        result = self.execute(self.task)
        self.task.refresh_from_db()
        self.assertTrue(self.task.workflow_column.is_terminal)
        self.execute(self.task, operation='undo', completion_id=result.data['id'])
        self.task.refresh_from_db()
        self.assertFalse(self.task.workflow_column.is_terminal)
    def test_legacy_writers_mirror_and_reconcile_is_repeatable(self):
        log = RoutineLog.objects.create(routine=self.routine, done_by=self.other, done_at=datetime.now(UTC))
        self.assertEqual(log.action_completion.actor_id, self.other.id)
        self.client.post(f'/api/tasks/{self.task.id}/toggle/', {}, format='json')
        self.assertEqual(self.task.unified_action.completions.count(), 1)
        for _ in range(2):
            call_command('reconcile_actions', stdout=StringIO())
        self.assertEqual(Action.objects.count(), 2)
        self.assertEqual(ActionCompletion.objects.count(), 2)
    def test_capture_explicit_create_retry_and_tenant_scope(self):
        body = {'title': 'Betten gemacht', 'create_new': True, 'request_id': str(uuid4()), 'duration_minutes': 5}
        path = f'/api/actions/capture/?family={self.family.id}'
        first = self.client.post(path, body, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        second = self.client.post(path, body, format='json')
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Routine.objects.filter(name='Betten gemacht').count(), 1)
        self.assertEqual(self.client.post(path, {'title': 'New', 'request_id': str(uuid4())}, format='json').status_code, 400)
    def test_settings_validate_schedule_and_tokens(self):
        path = f'/api/actions/routine/{self.routine.id}/'
        result = self.client.patch(path, {'schedule_text': 'jeden Montag um 18:00', 'icon': 'bed', 'accent_token': 'blue'}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.routine.refresh_from_db()
        self.assertEqual(self.routine.icon, 'bed')
        self.assertEqual(self.client.patch(path, {'accent_token': '#fff'}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(path, {'schedule': {'mode': 'static', 'recurrence': {'frequency': 'weekly', 'weekdays': ['XX']}}}, format='json').status_code, 400)

class ScheduleTests(SimpleTestCase):
    def schedule(self, **kwargs):
        return normalize_schedule({'mode': 'static', 'anchor_date': '2026-01-01', 'recurrence': {'frequency': 'daily'}, **kwargs}, 'Europe/Berlin')
    def test_weekday_windows_excluded_sunday(self):
        schedule = self.schedule(segments=[{'weekdays': ['MO','TU','WE','TH','FR'], 'preferred_time': '18:00', 'window': {'start': '17:00', 'end': '19:30'}}, {'weekdays': ['SA'], 'preferred_time': '14:00', 'window': {'start': '12:30', 'end': '16:00'}}], excluded_weekdays=['SU'])
        saturday = predict(schedule, [], datetime(2026,10,17,7,tzinfo=UTC))
        self.assertEqual(saturday['expected_at'].hour, 14)
        self.assertEqual(saturday['status'], 'scheduled')
        sunday = predict(schedule, [], datetime(2026,10,18,7,tzinfo=UTC))
        self.assertEqual(sunday['expected_at'].weekday(), 0)
    def test_long_monthly_nth_weekday(self):
        schedule = self.schedule(recurrence={'frequency': 'monthly', 'interval': 4, 'nth_weekdays': [{'weekday': 'TH', 'ordinal': 2}]})
        result = predict(schedule, [], datetime(2026,2,1,tzinfo=UTC))
        self.assertEqual(result['expected_at'].date().isoformat(), '2026-05-14')
    def test_dst_gap_fold_and_day_only(self):
        schedule = self.schedule(segments=[{'preferred_time': '02:30'}])
        gap = predict(schedule, [], datetime(2026,3,29,0,tzinfo=UTC))
        self.assertEqual(gap['expected_at'].hour, 3)
        fold = predict(schedule, [], datetime(2026,10,25,0,tzinfo=UTC))
        self.assertEqual(fold['expected_at'].fold, 0)
        day = predict(self.schedule(), [], datetime(2026,10,13,0,tzinfo=UTC))
        self.assertTrue(day['day_only'])
        self.assertEqual(day['expected_at'].hour, 12)
    def test_adaptive_proposal_outlier_static_and_rejection(self):
        history = [datetime(2026,8,1,12,tzinfo=UTC) + timedelta(weeks=i) for i in range(9)]
        now = datetime(2026,10,10,7,tzinfo=UTC)
        schedule = self.schedule(mode='adaptive', segments=[{'preferred_time': '18:00'}])
        result = predict(schedule, history, now)
        proposal = result['suggested_schedule_change']
        self.assertEqual(proposal['proposed']['preferred_time'], '14:00')
        self.assertEqual(result['expected_at'].hour, 18)
        self.assertIsNone(predict(schedule, history, now, [proposal['proposal_id']])['suggested_schedule_change'])
        schedule['mode'] = 'static'
        self.assertIsNone(predict(schedule, history, now)['suggested_schedule_change'])
        schedule['mode'] = 'learning'
        history.append(datetime(2026,10,3,20,tzinfo=UTC))
        self.assertEqual(predict(schedule, history, now)['expected_at'].hour, 14)
    def test_sparse_and_parser_contract(self):
        schedule = normalize_schedule({'mode': 'learning'}, 'Europe/Berlin')
        result = predict(schedule, [datetime(2026,10,12,12,tzinfo=UTC)], datetime(2026,10,13,7,tzinfo=UTC))
        self.assertLess(result['confidence'], .2)
        self.assertEqual(parse_schedule('alle 4 Monate am zweiten Donnerstag', 'Europe/Berlin')['recurrence']['nth_weekdays'][0]['ordinal'], 2)
        with self.assertRaises(ValueError):
            parse_schedule('arbitrary text', 'Europe/Berlin')

class ContextAndEventActionTests(UnifiedCompletionTests):
    def test_waste_execute_retry_undo_and_other_events_denied(self):
        from .models import FamilyEvent
        event = FamilyEvent.objects.create(family=self.family, title='Biotonne', type='waste.collection', starts_at=datetime.now(UTC))
        key = str(uuid4())
        path = f'/api/actions/events/?family={self.family.id}'
        body = {'action_id': f'event:{event.id}', 'request_id': key}
        first = self.client.post(path, body, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(self.client.post(path, body, format='json').data['id'], first.data['id'])
        # Different keys also address the same event occurrence.
        self.assertEqual(self.client.post(path, {**body, 'request_id': str(uuid4())}, format='json').data['id'], first.data['id'])
        self.assertEqual(ActionCompletion.objects.filter(action__legacy_event=event).count(), 1)
        undo = self.client.post(path, {**body, 'operation': 'undo', 'request_id': str(uuid4()), 'completion_id': first.data['id']}, format='json')
        self.assertEqual(undo.status_code, 200, undo.data)
        event.type = 'calendar.event'
        event.save()
        self.assertEqual(self.client.post(path, {**body, 'request_id': str(uuid4())}, format='json').status_code, 404)
    def test_context_private_note_and_foreign_reference_deny_without_orphan(self):
        from .notes_models import Note
        note = Note.objects.create(family=self.family, author=self.other, title='Private')
        path = f'/api/actions/from-context/?family={self.family.id}'
        before = Task.objects.count()
        denied = self.client.post(path, {'title': 'Explicit task', 'context': {'type': 'note', 'id': str(note.id)}}, format='json')
        self.assertEqual(denied.status_code, 404, denied.data)
        self.assertEqual(Task.objects.count(), before)
        note.author = self.user
        note.save()
        created = self.client.post(path, {'title': 'Explicit task', 'recurring': True, 'context': {'type': 'note', 'id': str(note.id)}}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(created.data['action_id'].startswith('routine:'))

class DecisionAndPolicyTests(UnifiedCompletionTests):
    def test_rounds_reference_canonical_decisions_without_copying_votes(self):
        from decisions.models import Decision, DecisionOption
        from .context_links import create_context_link
        template = Decision.objects.create(family=self.family, question='Meal plan?', created_by=self.user)
        DecisionOption.objects.create(decision=template, label='Pasta', position=0)
        DecisionOption.objects.create(decision=template, label='Soup', position=1)
        create_context_link(user=self.user, family=self.family, source_type='routine', source_id=self.routine.id, context_type='decision', context_id=template.id, relation_key='action.context')
        body = {'action_id': f'routine:{self.routine.id}', 'template_id':str(template.id), 'request_id':str(uuid4())}
        first = self.client.post('/api/actions/decision-round/', body, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        second = self.client.post('/api/actions/decision-round/', body, format='json')
        self.assertEqual(first.data['decision_id'], second.data['decision_id'])
        round_ = Decision.objects.get(pk=first.data['decision_id'])
        self.assertEqual(round_.options.count(), 2)
        self.assertEqual(round_.votes.count(), 0)
    def test_policies_are_personal_or_manager_controlled_and_calendar_off(self):
        path = f'/api/actions/settings/?family={self.family.id}'
        result = self.client.get(path)
        self.assertFalse(result.data['calendar_aware'])
        self.assertEqual(self.client.patch(path, {'capture_suggestions': False}, format='json').status_code, 200)
        self.assertFalse(self.client.get(f'/api/actions/capture/?family={self.family.id}').data['suggestions_enabled'])
        Membership.objects.filter(user=self.user, family=self.family).update(role='teen')
        self.assertEqual(self.client.patch(path, {'adaptive_enabled': False}, format='json').status_code, 403)
        self.assertEqual(self.client.patch(path, {'capture_suggestions': True}, format='json').status_code, 200)
    def test_recurring_task_completions_remain_legacy_workflow_compatible(self):
        row = self.task.unified_action
        row.schedule = normalize_schedule({'mode':'static', 'recurrence':{'frequency':'weekly','weekdays':['MO']}}, self.family.timezone)
        row.save()
        first = self.execute(self.task)
        second = self.execute(self.task)
        self.assertNotEqual(first.data['id'], second.data['id'])
        self.assertEqual(row.completions.filter(undone_at__isnull=True).count(), 2)
        self.execute(self.task, operation='undo', completion_id=first.data['id'])
        self.task.refresh_from_db()
        self.assertIsNotNone(self.task.completed_at)
    def test_duration_authorization(self):
        result = self.execute(self.task)
        path=f'/api/actions/completions/{result.data["id"]}/duration/'
        self.assertEqual(self.client.patch(path, {'duration_minutes':30}, format='json').status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(path, {'duration_minutes':15}, format='json').status_code, 403)
