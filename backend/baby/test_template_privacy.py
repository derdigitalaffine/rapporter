from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

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

        self.pregnancy.expected_due_date += timedelta(days=14)
        self.pregnancy.save(update_fields=['expected_due_date','updated_at'])
        second = pregnancy_template_items(self.owner, self.pregnancy, include_tasks=True, include_shopping=False)
        self.assertEqual(set(first['tasks']), set(second['tasks']))
        for task in Task.objects.filter(id__in=second['tasks']):
            self.assertEqual(task.due_at, old_due[task.id] + timedelta(days=14))
