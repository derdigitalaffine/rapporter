from datetime import date, timedelta
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from baby.models import BabyProfile, ManagedChildGuardian
from baby.child_identity_service import require_child_membership_guardian
from .family_relationship_models import FamilyRelationship
from .models import Family, FamilyEvent, Membership


class CalendarCustodySyncTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name='Custody calendar', slug='custody-calendar-747')
        self.owner = self.member('owner', 'owner')
        self.adult = self.member('adult', 'adult')
        self.child = self.member('child', 'child')
        self.client = APIClient()
        self.client.force_authenticate(self.owner.user)

    def member(self, name, role, family=None):
        user = get_user_model().objects.create_user('calendar-747-' + name)
        return Membership.objects.create(family=family or self.family, user=user, role=role, display_name=name)

    def custody(self, member=None, **kwargs):
        return FamilyRelationship.objects.create(family=self.family, child_membership=self.child,
            related_membership=member or self.owner, kind='parent', has_custody=True, **kwargs)

    def event_data(self, **kwargs):
        start = timezone.now() + timedelta(days=1)
        return {'family': str(self.family.pk), 'type': 'calendar.event', 'title': 'Child appointment',
            'starts_at': start.isoformat(), 'ends_at': (start + timedelta(hours=1)).isoformat(),
            'participants': [str(self.child.pk)], 'payload': {}, **kwargs}

    def sync(self, mutation):
        response = self.client.post('/api/sync/', {'protocol_version': 1, 'family_id': str(self.family.pk),
            'cursor': None, 'mutations': [mutation]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data['mutation_results'][0]

    def create_mutation(self, **kwargs):
        return {'mutation_id': str(uuid4()), 'entity_id': str(uuid4()), 'entity_type': 'event',
            'operation': 'create', 'base_version': None, 'data': self.event_data(), **kwargs}

    def test_existing_custody_without_baby_or_guardian_allows_rest_create_and_update(self):
        self.custody()
        self.assertFalse(BabyProfile.objects.filter(membership=self.child).exists())
        created = self.client.post('/api/events/', self.event_data(), format='json')
        self.assertEqual(created.status_code, 201, created.data)
        changed = self.client.patch(f"/api/events/{created.data['id']}/", {'title': 'Changed'}, format='json')
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(FamilyEvent.objects.get(pk=created.data['id']).title, 'Changed')
        self.assertFalse(ManagedChildGuardian.objects.exists())

    def test_multiple_custodians_and_dynamic_revocation_apply_to_sync(self):
        first = self.custody(); self.custody(self.adult)
        created = self.sync(self.create_mutation())
        self.assertEqual(created['status'], 'applied', created)
        self.client.force_authenticate(self.adult.user)
        update = {'mutation_id': str(uuid4()), 'entity_id': created['entity_id'], 'entity_type': 'event',
            'operation': 'update', 'base_version': created['version'], 'changes': {'title': 'Adult update'}}
        changed = self.sync(update)
        self.assertEqual(changed['status'], 'applied', changed)
        first.has_custody = False; first.save(update_fields=['has_custody'])
        self.client.force_authenticate(self.owner.user)
        denied = self.sync({**update, 'mutation_id': str(uuid4()), 'base_version': changed['version']})
        self.assertEqual((denied['status'], denied['code'], denied['http_status']), ('rejected', 'permission_denied', 403))
        self.assertIn('Sorgerecht', str(denied['errors']))
        self.assertEqual(FamilyEvent.objects.get(pk=created['entity_id']).title, 'Adult update')

    def test_roles_parenthood_and_inactive_custody_do_not_grant_access(self):
        relation = self.custody(status='inactive')
        for actor in [self.owner, self.adult]:
            self.client.force_authenticate(actor.user)
            result = self.client.post('/api/events/', self.event_data(), format='json')
            self.assertEqual(result.status_code, 403, result.data)
        relation.status = 'active'; relation.has_custody = False; relation.save()
        self.client.force_authenticate(self.owner.user)
        self.assertEqual(self.client.post('/api/events/', self.event_data(), format='json').status_code, 403)
        self.assertFalse(FamilyEvent.objects.filter(title='Child appointment').exists())

    def test_rejected_create_retry_is_currently_authorized_and_exactly_once(self):
        mutation = self.create_mutation()
        rejected = self.sync(mutation)
        self.assertEqual(rejected['code'], 'permission_denied', rejected)
        self.assertFalse(FamilyEvent.objects.filter(pk=mutation['entity_id']).exists())
        self.custody()
        retry = {**mutation, 'mutation_id': str(uuid4())}
        self.assertEqual(self.sync(retry)['status'], 'applied')
        self.assertEqual(self.sync(retry)['status'], 'already_applied')
        self.assertEqual(FamilyEvent.objects.filter(pk=mutation['entity_id']).count(), 1)

    def test_foreign_child_and_suspended_family_cannot_use_custody(self):
        self.custody()
        other = Family.objects.create(name='Other', slug='other-custody-747')
        foreign = self.member('foreign-child', 'child', other)
        result = self.client.post('/api/events/', self.event_data(participants=[str(foreign.pk)]), format='json')
        self.assertIn(result.status_code, [400, 403], result.data)
        self.family.status = 'suspended'; self.family.save(update_fields=['status'])
        result = self.client.post('/api/events/', self.event_data(), format='json')
        self.assertIn(result.status_code, [400, 403, 404], result.data)

    def test_legacy_guardian_and_custody_account_management_remain_compatible(self):
        baby = BabyProfile.objects.create(family=self.family, membership=self.child, display_name='Child', birth_date=date(2020, 1, 1))
        ManagedChildGuardian.objects.create(baby=baby, membership=self.adult, can_manage_account=False)
        self.client.force_authenticate(self.adult.user)
        self.assertEqual(self.client.post('/api/events/', self.event_data(), format='json').status_code, 201)
        self.custody(self.adult)
        _, authority = require_child_membership_guardian(self.adult.user, self.child, manage=True)
        self.assertTrue(authority.can_manage_account)
        self.assertEqual(authority.source, 'custody')
        response = self.client.get(f'/api/baby/memberships/{self.child.pk}/avatar/')
        self.assertEqual(response.status_code, 200, response.data)
