import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from family.models import Family, Membership

from .development_service import ensure_u_exam_events
from .family_modules import set_care_circle, set_module
from .models import PregnancyJournalEntry
from .pregnancy_service import create_managed_child, create_pregnancy, prenatal_calendar_event


User=get_user_model()


class BabyPrivacyTests(TestCase):
    def setUp(self):
        self.owner=User.objects.create_user(username='owner-privacy',password='pw')
        self.caregiver=User.objects.create_user(username='caregiver-privacy',password='pw')
        self.outside_manager=User.objects.create_user(username='outside-manager-privacy',password='pw')
        self.guest=User.objects.create_user(username='guest-privacy',password='pw')
        self.family=Family.objects.create(name='Privatfamilie',slug='baby-private',locale='de',timezone='Europe/Berlin')
        self.owner_membership=Membership.objects.create(family=self.family,user=self.owner,role=Membership.Role.OWNER,display_name='Alex')
        self.caregiver_membership=Membership.objects.create(family=self.family,user=self.caregiver,role=Membership.Role.ADULT,display_name='Sam')
        self.outside_manager_membership=Membership.objects.create(family=self.family,user=self.outside_manager,role=Membership.Role.ADULT,display_name='Taylor')
        self.guest_membership=Membership.objects.create(family=self.family,user=self.guest,role=Membership.Role.GUEST,display_name='Gast')
        set_module(self.owner,self.family,enabled=True,show_in_main_navigation=True)

    def _circle_with_caregiver(self):
        set_care_circle(self.owner,self.family,[
            {
                'membership':self.owner_membership.id,
                'can_view_pregnancy':True,
                'can_log_care':True,
                'can_view_growth_development':True,
                'is_guardian':True,
            },
            {
                'membership':self.caregiver_membership.id,
                'can_view_pregnancy':True,
                'can_log_care':True,
                'can_view_growth_development':True,
                'is_guardian':False,
            },
        ])

    def test_only_adults_can_receive_managed_child_guardian_rights(self):
        with self.assertRaises(ValidationError):
            set_care_circle(self.owner,self.family,[{
                'membership':self.guest_membership.id,
                'can_view_pregnancy':True,
                'can_log_care':True,
                'can_view_growth_development':True,
                'is_guardian':True,
            }])

    def test_manager_outside_care_circle_cannot_modify_pregnancy(self):
        pregnancy=create_pregnancy(self.owner,self.family,expected_due_date=date.today()+timedelta(days=100))
        client=APIClient();client.force_authenticate(self.outside_manager)
        response=client.patch(f'/api/baby/pregnancies/{pregnancy.id}/',{'notes':'must stay private'},format='json')
        self.assertEqual(response.status_code,403)
        pregnancy.refresh_from_db()
        self.assertEqual(pregnancy.notes,'')

    def test_non_guardian_caregiver_cannot_complete_birth_or_create_child_identity(self):
        self._circle_with_caregiver()
        pregnancy=create_pregnancy(self.owner,self.family,expected_due_date=date.today()+timedelta(days=1))
        expected=pregnancy.expected_babies.get()
        client=APIClient();client.force_authenticate(self.caregiver)
        birth=client.post(f'/api/baby/pregnancies/{pregnancy.id}/birth/',{
            'babies':[{
                'pregnancy_baby':str(expected.id),
                'display_name':'Mia',
                'birth_date':date.today().isoformat(),
                'gestational_age_weeks':40,
                'growth_reference_sex':'female',
            }]
        },format='json')
        self.assertEqual(birth.status_code,403)
        direct=client.post('/api/baby/profiles/',{
            'family':str(self.family.id),
            'client_identity_key':str(uuid.uuid4()),
            'display_name':'Mia',
            'birth_date':date.today().isoformat(),
            'gestational_age_weeks':40,
            'growth_reference_sex':'female',
        },format='json')
        self.assertEqual(direct.status_code,403)
        self.assertFalse(Membership.objects.filter(family=self.family,role=Membership.Role.CHILD).exists())

    def test_preventive_calendar_event_does_not_expose_child_identity_or_exam(self):
        baby=create_managed_child(
            self.owner,self.family,display_name='Mia',birth_date=date.today()-timedelta(days=120),
            gestational_age_weeks=40,growth_reference_sex='female',client_identity_key=uuid.uuid4(),
        )
        events=ensure_u_exam_events(self.owner,baby.id)
        self.assertTrue(events)
        for event in events:
            serialized=f'{event.title} {event.external_id} {event.payload}'
            self.assertNotIn(str(baby.id),serialized)
            self.assertNotIn('Mia',serialized)
            self.assertNotRegex(serialized,r'\bU(?:2|3|4|5|6|7|7a|8|9)\b')
            self.assertEqual(event.title,'Vorsorgetermin')
            self.assertEqual(set(event.payload),{'deep_link','private_context'})
            self.assertTrue(event.external_id.startswith('familyos-private:'))

    def test_prenatal_calendar_event_keeps_private_title_and_note_inside_care_domain(self):
        pregnancy=create_pregnancy(self.owner,self.family,expected_due_date=date.today()+timedelta(days=100))
        event=prenatal_calendar_event(
            self.owner,pregnancy,title='Hebamme – sensible Besprechung',starts_at=timezone.now()+timedelta(days=2),
            event_type='baby.midwife',payload={'note':'Private medizinische Notiz'},
        )
        public=f'{event.title} {event.external_id} {event.payload}'
        self.assertNotIn(str(pregnancy.id),public)
        self.assertNotIn('Hebamme',public)
        self.assertNotIn('medizinische',public)
        self.assertEqual(event.title,'Termin')
        self.assertEqual(set(event.payload),{'deep_link','private_context'})
        self.assertTrue(event.external_id.startswith('familyos-private:'))
        journal=PregnancyJournalEntry.objects.get(pregnancy=pregnancy)
        self.assertIn('Hebamme',journal.note)
        self.assertIn('Private medizinische Notiz',journal.note)

    def test_disabling_module_removes_main_nav_visibility_but_keeps_domain_data(self):
        pregnancy=create_pregnancy(self.owner,self.family,expected_due_date=date.today()+timedelta(days=100))
        setting=set_module(self.owner,self.family,enabled=False)
        self.assertFalse(setting.enabled)
        self.assertFalse(setting.show_in_main_navigation)
        self.assertTrue(type(pregnancy).objects.filter(pk=pregnancy.pk).exists())
