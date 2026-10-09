from datetime import date, datetime, timedelta, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .birthdays import calendar_projection, next_occurrence, project, run_birthday_reminders
from .models import BirthdayGiftPlan, BirthdayPerson, BirthdayReminder, EntryMemory, Family, FamilyEvent, Membership, ShoppingItem, Task, UserProfile
from .models_features import NotificationPreference


class BirthdayTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.owner=User.objects.create_user(username='birthday-owner')
        self.mia=User.objects.create_user(username='mia')
        self.family=Family.objects.create(name='Birthday',slug='birthday')
        self.owner_member=Membership.objects.create(family=self.family,user=self.owner,role='owner')
        self.mia_member=Membership.objects.create(family=self.family,user=self.mia,role='adult',display_name='Mia',birthday_visibility='day_month')
        UserProfile.objects.create(user=self.mia,birth_month=3,birth_day=12,birth_year=2016)
        self.client=APIClient();self.client.force_authenticate(self.owner)
        self.key=f'member:{self.mia_member.id}'

    def rows(self,response):return response.data.get('results',response.data)

    def test_occurrences_age_unknown_year_and_leap_day(self):
        self.assertEqual(next_occurrence(2,29,date(2027,1,1)),date(2027,2,28))
        self.assertEqual(next_occurrence(2,29,date(2028,1,1)),date(2028,2,29))
        self.assertEqual(next_occurrence(1,1,date(2026,12,31)),date(2027,1,1))
        row=project(self.family,self.owner,date(2026,3,12))[0]
        self.assertEqual(row['days_until'],0);self.assertIsNone(row['turning_age'])
        self.mia_member.birthday_visibility='full_date';self.mia_member.save()
        self.assertEqual(project(self.family,self.owner,date(2026,3,12))[0]['turning_age'],10)
        BirthdayPerson.objects.create(family=self.family,name='Oma',birth_month=3,birth_day=13)
        self.assertIsNone(project(self.family,self.owner,date(2026,3,12))[1]['turning_age'])

    def test_hidden_profiles_and_own_gift_details(self):
        self.mia_member.birthday_visibility='hidden';self.mia_member.save()
        self.assertEqual(project(self.family,self.owner),[])
        own=project(self.family,self.mia)[0]
        self.assertFalse(own['can_plan']);self.assertNotIn('gift_status',own);self.assertNotIn('idea_text',own)

    def test_virtual_calendar_has_one_occurrence_and_no_database_event(self):
        rows=calendar_projection(self.family,self.owner,date(2026,1,1),date(2026,12,31))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['type'],'birthday')
        self.assertTrue(rows[0]['payload']['all_day']);self.assertFalse(FamilyEvent.objects.exists())
        response=self.client.get('/api/events/',{'family':str(self.family.id),'start':'2026-01-01','end':'2026-12-31'})
        self.assertEqual(response.status_code,200);self.assertEqual(len(self.rows(response)),1)

    def test_external_person_validation_and_cross_family_isolation(self):
        base={'family':str(self.family.id),'name':'Oma','birth_month':2,'birth_day':29}
        response=self.client.post('/api/birthday-people/',base,format='json')
        self.assertEqual(response.status_code,201,response.data)
        response=self.client.post('/api/birthday-people/',{**base,'birth_year':2025},format='json')
        self.assertEqual(response.status_code,400)
        other=Family.objects.create(name='Other',slug='birthday-other')
        BirthdayPerson.objects.create(family=other,name='Secret',birth_month=1,birth_day=1)
        response=self.client.get('/api/birthday-people/')
        self.assertEqual(len(self.rows(response)),1)
        response=self.client.get('/api/birthdays/',{'family':str(other.id)})
        self.assertEqual(response.status_code,403)

    def gift(self,**kwargs):
        response=self.client.post('/api/birthday-gift-plans/',{'family':str(self.family.id),'birthday_key':self.key,**kwargs},format='json')
        self.assertEqual(response.status_code,200,response.data)
        return response

    def test_gift_actions_are_idempotent_and_hidden_everywhere(self):
        self.gift(idea_text='Geheimes Fahrrad',action='task')
        self.gift(idea_text='Geheimes Fahrrad',action='task')
        self.gift(idea_text='Geheimes Fahrrad',action='shopping')
        self.assertEqual(Task.objects.count(),1);self.assertEqual(ShoppingItem.objects.count(),1)
        self.assertFalse(EntryMemory.objects.exists())
        task=Task.objects.get();item=ShoppingItem.objects.get()
        self.client.force_authenticate(self.mia)
        for path in ['/api/tasks/','/api/shopping-lists/','/api/task-lists/','/api/dashboard/']:
            response=self.client.get(path,{'family':str(self.family.id)})
            self.assertEqual(response.status_code,200,response.data)
            self.assertNotIn('Geheimes Fahrrad',str(response.data));self.assertNotIn(task.title,str(response.data))
            if path=='/api/task-lists/':self.assertEqual(self.rows(response)[0]['open_count'],0)
            if path=='/api/shopping-lists/':self.assertEqual(self.rows(response)[0]['items'],[])
        self.assertEqual(self.client.get(f'/api/tasks/{task.id}/').status_code,404)
        self.assertEqual(self.client.get(f'/api/shopping-items/{item.id}/').status_code,404)
        self.assertEqual(self.client.post(f'/api/smart/shopping/{item.id}/favorite/').status_code,404)
        response=self.client.get('/api/birthdays/',{'family':str(self.family.id)})
        own=response.data['birthdays'][0]
        self.assertNotIn('idea_text',own);self.assertNotIn('gift_status',own)
        response=self.client.post('/api/birthday-gift-plans/',{'family':str(self.family.id),'birthday_key':self.key,'idea_text':'Self'},format='json')
        self.assertEqual(response.status_code,403)

    def test_completion_and_reopen_sync_gift_status(self):
        self.gift(action='task');task=Task.objects.get()
        self.client.post(f'/api/tasks/{task.id}/toggle/')
        row=project(self.family,self.owner)[0];self.assertEqual(row['gift_status'],'ready')
        self.client.post(f'/api/tasks/{task.id}/toggle/')
        row=project(self.family,self.owner)[0];self.assertEqual(row['gift_status'],'planned')

    @patch('family.birthdays.send_user_push',return_value={'sent':1,'errors':0})
    def test_reminder_cadence_timezone_preferences_and_idempotency(self,push):
        for days in [21,7,1,0]:
            now=datetime(2027,3,12,9,tzinfo=utc.utc)-timedelta(days=days)
            with self.subTest(stage=days):
                before=push.call_count
                run_birthday_reminders(now);run_birthday_reminders(now)
                self.assertEqual(push.call_count-before,1 if days in {21,7} else 2)
        self.assertEqual(BirthdayReminder.objects.count(),6)
        BirthdayReminder.objects.all().delete();BirthdayGiftPlan.objects.create(family=self.family,membership=self.mia_member,occurrence_year=2027,status='ready')
        before=push.call_count;run_birthday_reminders(datetime(2027,3,5,9,tzinfo=utc.utc));self.assertEqual(push.call_count,before)
        NotificationPreference.objects.create(membership=self.owner_member,birthdays=False)
        before=push.call_count;run_birthday_reminders(datetime(2027,3,11,9,tzinfo=utc.utc));self.assertEqual(push.call_count-before,1)
        before=push.call_count;run_birthday_reminders(datetime(2028,3,12,0,tzinfo=utc.utc));self.assertEqual(push.call_count,before)

    @patch('family.birthdays.send_user_push',return_value={'sent':1,'errors':0})
    def test_inactive_and_late_add_do_not_send_old_stages(self,push):
        self.mia_member.birthday_visibility='hidden';self.mia_member.save()
        person=BirthdayPerson.objects.create(family=self.family,name='Oma',birth_month=3,birth_day=12,active=False)
        run_birthday_reminders(datetime(2027,3,5,9,tzinfo=utc.utc))
        self.assertEqual(push.call_count,0)
        person.active=True;person.save()
        run_birthday_reminders(datetime(2027,3,7,9,tzinfo=utc.utc))
        self.assertEqual(push.call_count,0)
