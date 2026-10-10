from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership, Task

from .family_modules import set_module
from .pregnancy_service import create_pregnancy
from .template_service import pregnancy_template_items

User = get_user_model()

class PregnancyTemplatePrivacyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='template-owner', password='pw')
        self.family = Family.objects.create(name='Template Family', slug='template-family', locale='de', timezone='Europe/Berlin')
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name='Alex')
        set_module(self.owner, self.family, enabled=True)
        self.pregnancy = create_pregnancy(self.owner, self.family, expected_due_date=date.today()+timedelta(days=120))
        self.client = APIClient(); self.client.force_authenticate(self.owner)

    def test_shared_tasks_hide_private_context_and_recalculate_after_due_date_change(self):
        first = pregnancy_template_items(self.owner, self.pregnancy, include_tasks=True, include_shopping=False)
        tasks = list(Task.objects.filter(id__in=first['tasks']).order_by('title'))
        self.assertEqual(len(tasks), 3)
        for task in tasks:
            public = f'{task.title} {task.source} {task.tags} {task.task_list.name}'
            self.assertNotIn(str(self.pregnancy.id), public)
            self.assertNotIn('Kinderarzt', public)
            self.assertNotIn('pregnancy', public.lower())
            self.assertNotIn('baby', public.lower())
        old_due = {task.id: task.due_at for task in tasks}

        new_due = self.pregnancy.expected_due_date + timedelta(days=14)
        response = self.client.patch(
            f'/api/baby/pregnancies/{self.pregnancy.id}/',
            {'expected_due_date': new_due.isoformat()},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        for task in Task.objects.filter(id__in=first['tasks']):
            self.assertEqual(task.due_at, old_due[task.id] + timedelta(days=14))
