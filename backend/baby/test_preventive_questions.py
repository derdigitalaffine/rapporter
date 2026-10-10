import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership

from .family_modules import set_module
from .pregnancy_service import create_managed_child

User = get_user_model()

class PreventiveQuestionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='preventive-owner', password='pw')
        self.family = Family.objects.create(name='Preventive Family', slug='preventive-family', locale='de', timezone='Europe/Berlin')
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name='Alex')
        set_module(self.owner, self.family, enabled=True)
        self.baby = create_managed_child(self.owner, self.family, display_name='Mia', birth_date=date.today()-timedelta(days=100), gestational_age_weeks=40, growth_reference_sex='female', client_identity_key=uuid.uuid4())
        self.client = APIClient(); self.client.force_authenticate(self.owner)

    def test_questions_are_linked_to_private_preventive_event_and_returned(self):
        planned = self.client.post(f'/api/baby/profiles/{self.baby.id}/preventive-events/', {}, format='json')
        self.assertEqual(planned.status_code, 200, planned.data)
        event = planned.data['events'][0]
        question = self.client.post(
            f'/api/baby/profiles/{self.baby.id}/appointment-questions/',
            {'event': event['id'], 'text': 'Wie hat sich das Gewicht entwickelt?'},
            format='json',
        )
        self.assertEqual(question.status_code, 201, question.data)
        data = self.client.get(f'/api/baby/profiles/{self.baby.id}/development/?language=de')
        self.assertEqual(data.status_code, 200, data.data)
        appointments = data.data['preventive_appointments']
        self.assertTrue(appointments)
        matching = next(row for row in appointments if row['id'] == event['id'])
        self.assertEqual(matching['questions'][0]['text'], 'Wie hat sich das Gewicht entwickelt?')
        self.assertRegex(matching['exam'], r'^U(?:2|3|4|5|6|7|7a|8|9)$')
