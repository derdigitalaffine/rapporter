from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient

from .context_links import create_context_link
from .context_models import ContextLink
from .models import Family, Membership, Note, Task
from .travel_models import Trip


class NotesExtendedTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.author = User.objects.create_user(username='extended-author')
        self.editor = User.objects.create_user(username='extended-editor')
        self.reader = User.objects.create_user(username='extended-reader')
        self.other = User.objects.create_user(username='extended-other')
        self.family = Family.objects.create(name='Extended Notes', slug='extended-notes')
        self.other_family = Family.objects.create(name='Other Notes', slug='other-extended-notes')
        Membership.objects.create(family=self.family, user=self.author, role=Membership.Role.ADULT)
        Membership.objects.create(family=self.family, user=self.editor, role=Membership.Role.TEEN)
        Membership.objects.create(family=self.family, user=self.reader, role=Membership.Role.CHILD)
        self.other_membership = Membership.objects.create(family=self.other_family, user=self.other, role=Membership.Role.ADULT)
        self.client = APIClient()
        self.client.force_authenticate(self.author)

    def create_extended(self, *, assignee=None):
        item = {'id': 'pack-passport', 'text': 'Pass einpacken', 'checked': False, 'due_at': '2030-01-02T12:00:00Z'}
        if assignee is not None:
            item['assignee'] = assignee
        response = self.client.post(
            '/api/notes/',
            {
                'family': str(self.family.id),
                'title': 'Reiseplan',
                'body': 'Simple fallback remains available',
                'extended_mode': True,
                'blocks': [
                    {'type': 'heading', 'level': 2, 'text': 'Vorbereitung'},
                    {'type': 'panel', 'tone': 'info', 'text': 'Nur sichere strukturierte Blöcke.'},
                    {'type': 'checklist', 'items': [item]},
                ],
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def share(self, note, user, permission):
        return self.client.post(
            f"/api/notes/{note['id']}/sharing/",
            {'version': note['version'], 'shares': [{'user': user.id, 'permission': permission}]},
            format='json',
        )

    def test_simple_note_contract_stays_default_and_blocks_require_opt_in(self):
        simple = self.client.post(
            '/api/notes/',
            {'family': str(self.family.id), 'title': 'Schnell', 'body': '<script>plain text</script>'},
            format='json',
        )
        self.assertEqual(simple.status_code, 201, simple.data)
        self.assertFalse(simple.data['extended_mode'])
        self.assertEqual(simple.data['blocks'], [])

        rejected = self.client.post(
            '/api/notes/',
            {
                'family': str(self.family.id),
                'title': 'No opt-in',
                'blocks': [{'type': 'paragraph', 'text': 'Structured'}],
            },
            format='json',
        )
        self.assertEqual(rejected.status_code, 400)

    def test_block_schema_is_allowlisted_bounded_and_optimistically_versioned(self):
        note = self.create_extended()
        url = f"/api/notes/{note['id']}/"
        valid = [
            {'type': 'paragraph', 'text': '<b>render as text</b>'},
            {'type': 'heading', 'level': 3, 'text': 'Abschnitt'},
            {'type': 'panel', 'tone': 'warning', 'text': 'Achtung'},
            {'type': 'checklist', 'items': [{'id': 'one', 'text': 'Ein Punkt', 'checked': True}]},
        ]
        updated = self.client.patch(url, {'version': 1, 'blocks': valid}, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['version'], 2)
        self.assertEqual(self.client.patch(url, {'version': 1, 'blocks': []}, format='json').status_code, 409)
        self.assertEqual(self.client.patch(url, {'version': 2, 'blocks': [{'type': 'html', 'html': '<script>x</script>'}]}, format='json').status_code, 400)

        history = self.client.get(url + 'history/').data
        rows = history.get('results', history)
        self.assertEqual(rows[0]['version'], 2)
        self.assertTrue(rows[0]['extended_mode'])
        self.assertEqual(rows[0]['blocks'], valid)

    def test_checklist_conversion_creates_exactly_one_canonical_task_and_copies_metadata(self):
        note = self.create_extended(assignee=self.editor.id)
        trip = Trip.objects.create(
            family=self.family,
            title='Japan',
            stage='planning',
            date_precision='unknown',
            created_by=self.author,
        )
        create_context_link(
            user=self.author,
            family=self.family,
            source_type='note',
            source_id=note['id'],
            context_type='trip',
            context_id=trip.id,
        )

        url = f"/api/notes/{note['id']}/checklist-task/"
        first = self.client.post(url, {'item_id': 'pack-passport'}, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertTrue(first.data['created'])
        task = Task.objects.get(pk=first.data['task']['id'])
        self.assertEqual(task.family, self.family)
        self.assertEqual(task.title, 'Pass einpacken')
        self.assertEqual(task.assignee_id, self.editor.id)
        self.assertEqual(task.due_at, parse_datetime('2030-01-02T12:00:00Z'))
        self.assertEqual(task.source, 'note_checklist')
        self.assertEqual(task.task_list.family, self.family)
        self.assertTrue(
            ContextLink.objects.filter(
                family=self.family,
                source_type='task',
                source_id=task.id,
                context_type='trip',
                context_id=trip.id,
            ).exists()
        )

        second = self.client.post(url, {'item_id': 'pack-passport'}, format='json')
        self.assertEqual(second.status_code, 200, second.data)
        self.assertFalse(second.data['created'])
        self.assertEqual(second.data['task']['id'], str(task.id))
        self.assertEqual(Task.objects.filter(family=self.family, source='note_checklist').count(), 1)

        stored = Note.objects.get(pk=note['id'])
        self.assertEqual(stored.version, 2)
        checklist = next(block for block in stored.blocks if block['type'] == 'checklist')
        self.assertEqual(checklist['items'][0]['task_id'], str(task.id))
        revision = stored.revisions.get(version=2)
        self.assertEqual(revision.blocks[-1]['items'][0]['task_id'], str(task.id))

    def test_sharing_permissions_and_assignee_tenant_boundary_are_preserved(self):
        cross_family = self.client.post(
            '/api/notes/',
            {
                'family': str(self.family.id),
                'title': 'Bad assignee',
                'extended_mode': True,
                'blocks': [
                    {
                        'type': 'checklist',
                        'items': [{'id': 'x', 'text': 'No', 'checked': False, 'assignee': self.other.id}],
                    }
                ],
            },
            format='json',
        )
        self.assertEqual(cross_family.status_code, 400)

        note = self.create_extended()
        shared = self.share(note, self.reader, 'read')
        self.assertEqual(shared.status_code, 200, shared.data)
        self.client.force_authenticate(self.reader)
        self.assertEqual(
            self.client.post(f"/api/notes/{note['id']}/checklist-task/", {'item_id': 'pack-passport'}, format='json').status_code,
            403,
        )

        self.client.force_authenticate(self.author)
        forged = self.client.patch(
            f"/api/notes/{note['id']}/",
            {
                'version': shared.data['version'],
                'blocks': [
                    {
                        'type': 'checklist',
                        'items': [
                            {
                                'id': 'pack-passport',
                                'text': 'Pass einpacken',
                                'checked': False,
                                'task_id': '00000000-0000-0000-0000-000000000001',
                            }
                        ],
                    }
                ],
            },
            format='json',
        )
        self.assertEqual(forged.status_code, 400)
