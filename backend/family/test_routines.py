from datetime import datetime, timedelta, timezone as tz
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, Routine, RoutineLog, RoutineReminderState
from .models_features import NotificationPreference
from .predictions import routine_prediction
from .routine_reminders import run_routine_reminders


class RoutineTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('owner')
        self.other=get_user_model().objects.create_user('other')
        self.family=Family.objects.create(name='Home',slug='routine-home',timezone='Europe/Berlin')
        self.member=Membership.objects.create(family=self.family,user=self.user,role='owner')
        Membership.objects.create(family=self.family,user=self.other,role='adult')
        self.client=APIClient();self.client.force_authenticate(self.user)
        self.now=datetime(2026,10,10,10,tzinfo=tz.utc)

    def test_name_only_and_goal_validation(self):
        response=self.client.post('/api/routines/',{'family':str(self.family.id),'name':'Lüften'},format='json')
        self.assertEqual(response.status_code,201)
        self.assertIsNone(response.data['prediction']['expected_at'])
        path=f"/api/routines/{response.data['id']}/"
        self.assertEqual(self.client.patch(path,{'target_count':3,'target_period_days':7},format='json').status_code,200)
        for payload in [{'target_count':0},{'target_count':101},{'target_period_days':0},{'target_count':100,'target_period_days':1}]:
            self.assertEqual(self.client.patch(path,payload,format='json').status_code,400)

    def test_routines_are_editable_and_deletable(self):
        row=Routine.objects.create(family=self.family,name='Bad putzen',suggested_interval_days=7,icon='sparkles')
        path=f'/api/routines/{row.id}/'
        changed=self.client.patch(path,{'name':'Bad komplett reinigen','active':False},format='json')
        self.assertEqual(changed.status_code,200)
        row.refresh_from_db();self.assertEqual(row.name,'Bad komplett reinigen');self.assertFalse(row.active)
        self.assertEqual(self.client.delete(path).status_code,204)
        self.assertFalse(Routine.objects.filter(pk=row.pk).exists())

    @patch.dict('os.environ',{
        'DJANGO_SUPERUSER_USERNAME':'routine-bootstrap-admin',
        'DJANGO_SUPERUSER_PASSWORD':'routine-bootstrap-admin-password',
        'INITIAL_OWNER_USERNAME':'routine-bootstrap-owner',
        'INITIAL_OWNER_PASSWORD':'routine-bootstrap-owner-password',
        'INITIAL_FAMILY_NAME':'Bootstrap Familie',
        'TIME_ZONE':'Europe/Berlin',
    },clear=False)
    def test_bootstrap_does_not_restore_changed_or_deleted_starter_routines(self):
        Family.objects.filter(slug='meine-familie').delete()
        call_command('bootstrap_famuhle')
        family=Family.objects.get(slug='meine-familie')
        starters=Routine.objects.filter(family=family)
        self.assertEqual(starters.count(),4)
        deleted=starters.get(name='Bad putzen');deleted.delete()
        renamed=starters.get(name='Bettwäsche wechseln');renamed.name='Bettwäsche frisch beziehen';renamed.save(update_fields=['name','updated_at'])
        call_command('bootstrap_famuhle')
        names=set(Routine.objects.filter(family=family).values_list('name',flat=True))
        self.assertNotIn('Bad putzen',names)
        self.assertNotIn('Bettwäsche wechseln',names)
        self.assertIn('Bettwäsche frisch beziehen',names)
        self.assertEqual(len(names),3)

    def test_goal_and_history_never_delay_wish(self):
        row=Routine.objects.create(family=self.family,name='Bettwäsche',target_count=1,target_period_days=7)
        Routine.objects.filter(pk=row.pk).update(created_at=self.now-timedelta(days=8));row.refresh_from_db()
        self.assertEqual(routine_prediction(row,self.now)['status'],'overdue')
        for days in [90,60,30]:
            RoutineLog.objects.create(routine=row,done_at=self.now-timedelta(days=days),done_by=self.user)
        result=routine_prediction(row,self.now)
        self.assertEqual(result['learned_interval_days'],30)
        self.assertLessEqual(result['expected_interval_days'],7)
        row.target_count=3;row.target_period_days=1
        self.assertAlmostEqual(routine_prediction(row,self.now)['target_interval_days'],.333,places=3)

    def test_idempotent_record_and_undo(self):
        row=Routine.objects.create(family=self.family,name='Boden',target_count=1,target_period_days=7)
        token=str(uuid4());path=f'/api/routines/{row.id}/done/'
        first=self.client.post(path,{'request_id':token},format='json')
        second=self.client.post(path,{'request_id':token},format='json')
        self.assertEqual(first.status_code,201);self.assertEqual(second.status_code,200)
        self.assertEqual(first.data['id'],second.data['id']);self.assertEqual(row.logs.count(),1)
        self.assertEqual(self.client.delete(f"/api/routines/{row.id}/logs/{first.data['id']}/").status_code,204)
        self.assertEqual(row.logs.count(),0)
        row.active=False;row.save()
        self.assertEqual(self.client.post(path,{},format='json').status_code,400)

    def test_isolation_snooze_and_log_permissions(self):
        foreign=Family.objects.create(name='Other',slug='routine-other')
        Membership.objects.create(family=foreign,user=self.other)
        row=Routine.objects.create(family=foreign,name='Secret')
        self.assertEqual(self.client.post(f'/api/routines/{row.id}/done/',{},format='json').status_code,404)
        own=Routine.objects.create(family=self.family,name='Shared')
        self.client.post(f'/api/routines/{own.id}/snooze/',{'hours':24},format='json')
        self.assertEqual(RoutineReminderState.objects.get(routine=own).membership,self.member)
        log=RoutineLog.objects.create(routine=own,done_by=self.user,done_at=self.now)
        Membership.objects.filter(family=self.family,user=self.other).update(role='teen')
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(f'/api/routines/{own.id}/logs/{log.id}/').status_code,403)

    @patch('family.routine_reminders.send_user_push',return_value={'sent':1,'errors':0})
    def test_reminder_quiet_preferences_and_cycle(self,push):
        row=Routine.objects.create(family=self.family,name='Lüften',target_count=1,target_period_days=1)
        RoutineLog.objects.create(routine=row,done_at=self.now-timedelta(days=2),done_by=self.user)
        NotificationPreference.objects.create(membership=self.member,routines=False)
        self.assertEqual(run_routine_reminders(self.now.replace(hour=3)),0)
        self.assertEqual(run_routine_reminders(self.now),1)
        self.assertEqual(run_routine_reminders(self.now),0)
        self.assertEqual(run_routine_reminders(self.now+timedelta(days=1)),0)
        self.assertIn('family=',push.call_args.args[3])
        RoutineLog.objects.create(routine=row,done_at=self.now+timedelta(hours=1),done_by=self.user)
        self.assertEqual(run_routine_reminders(self.now+timedelta(days=2)),1)

    @patch('family.routine_reminders.send_user_push',return_value={'sent':0,'errors':1})
    def test_failed_push_retryable(self,push):
        row=Routine.objects.create(family=self.family,name='Retry',target_count=1,target_period_days=1)
        RoutineLog.objects.create(routine=row,done_at=self.now-timedelta(days=2))
        self.assertEqual(run_routine_reminders(self.now),0)
        self.assertFalse(RoutineReminderState.objects.exclude(last_sent_at=None).exists())
        self.assertEqual(run_routine_reminders(self.now+timedelta(minutes=5)),0)
        self.assertEqual(push.call_count,4)
