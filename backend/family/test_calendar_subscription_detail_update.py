import base64
import plistlib
from datetime import datetime, timezone as utc

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from icalendar import Calendar

from telemetry.models import AuditEvent
from .models import Family, FamilyEvent, Membership


@override_settings(APP_URL='https://calendar.example.test', AUTH_ABUSE_HMAC_KEY='calendar-detail-tests', DEBUG=True)
class CalendarSubscriptionDetailUpdateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('detail-owner', password='calendar-test-password')
        self.family = Family.objects.create(name='Detail Family', slug='detail-family', timezone='Europe/Berlin')
        self.membership = Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER, display_name='Alex')
        self.event = FamilyEvent.objects.create(
            family=self.family,
            type='calendar.event',
            title='Private family title',
            starts_at=datetime(2026, 10, 20, 8, tzinfo=utc.utc),
            ends_at=datetime(2026, 10, 20, 9, tzinfo=utc.utc),
            is_family_event=True,
            payload={'location': 'Secret place', 'description': 'Never exported'},
        )
        self.event.participants.add(self.membership)
        self.client = APIClient()
        login = self.client.post('/api/auth/login/', {'username': self.user.username, 'password': 'calendar-test-password'}, format='json')
        self.assertEqual(login.status_code, 200, login.data)
        self.public = APIClient()
        self.path = f'/api/calendar-subscriptions/{self.family.pk}/'

    def make_event(self, title, *, family_event=True, participant=None):
        event = FamilyEvent.objects.create(
            family=self.family,
            type='calendar.event',
            title=title,
            starts_at=datetime(2026, 10, 21, 8, tzinfo=utc.utc),
            ends_at=datetime(2026, 10, 21, 9, tzinfo=utc.utc),
            is_family_event=family_event,
        )
        if participant is not None:
            event.participants.add(participant)
        return event

    def test_detail_level_changes_existing_link_without_rotating_token(self):
        created = self.client.post(self.path, {'name': 'Existing iPhone', 'detail_level': 'title'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        detail = self.path + created.data['id'] + '/'
        subscription_url = created.data['subscription_url']
        feed = subscription_url.replace('https://calendar.example.test', '')

        initial = Calendar.from_ical(self.public.get(feed).content).walk('VEVENT')[0]
        self.assertEqual(str(initial['SUMMARY']), 'Private family title')
        self.assertNotIn('LOCATION', initial)

        updated = self.client.patch(detail, {'detail_level': 'availability'}, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['detail_level'], 'availability')
        after = Calendar.from_ical(self.public.get(feed).content).walk('VEVENT')[0]
        self.assertEqual(str(after['SUMMARY']), 'Belegt')
        self.assertNotIn('LOCATION', after)
        self.assertNotIn('DESCRIPTION', after)

        revealed = self.client.post(detail + 'reveal/')
        self.assertEqual(revealed.status_code, 200, revealed.data)
        self.assertEqual(revealed.data['subscription_url'], subscription_url)
        self.assertEqual(revealed.data['detail_level'], 'availability')
        self.assertEqual(AuditEvent.objects.filter(event_key='calendar.subscription.updated').count(), 1)

        full = self.client.patch(detail, {'detail_level': 'full'}, format='json')
        self.assertEqual(full.status_code, 200, full.data)
        expanded = Calendar.from_ical(self.public.get(feed).content).walk('VEVENT')[0]
        self.assertEqual(str(expanded['SUMMARY']), 'Private family title')
        self.assertEqual(str(expanded['LOCATION']), 'Secret place')
        self.assertNotIn('DESCRIPTION', expanded)

    def test_invalid_detail_level_is_rejected_without_changing_grant(self):
        created = self.client.post(self.path, {'name': 'Device', 'detail_level': 'title'}, format='json')
        detail = self.path + created.data['id'] + '/'
        rejected = self.client.patch(detail, {'detail_level': 'everything'}, format='json')
        self.assertEqual(rejected.status_code, 400)
        listing = self.client.get(self.path)
        self.assertEqual(listing.data['subscriptions'][0]['detail_level'], 'title')

    def test_scope_only_accepts_active_children_and_teens(self):
        child_user = get_user_model().objects.create_user('scope-child')
        child = Membership.objects.create(family=self.family, user=child_user, role=Membership.Role.CHILD, display_name='Sam')
        teen_user = get_user_model().objects.create_user('scope-teen')
        teen = Membership.objects.create(family=self.family, user=teen_user, role=Membership.Role.TEEN, display_name='Taylor')
        adult_user = get_user_model().objects.create_user('scope-adult')
        adult = Membership.objects.create(family=self.family, user=adult_user, role=Membership.Role.ADULT, display_name='Morgan')

        listing = self.client.get(self.path)
        self.assertEqual({row['id'] for row in listing.data['selectable_members']}, {str(child.pk), str(teen.pk)})

        rejected = self.client.post(self.path, {
            'name': 'Invalid scope',
            'detail_level': 'title',
            'included_member_ids': [str(adult.pk)],
        }, format='json')
        self.assertEqual(rejected.status_code, 400)

        created = self.client.post(self.path, {
            'name': 'Kids scope',
            'detail_level': 'title',
            'included_member_ids': [str(child.pk), str(teen.pk)],
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['included_member_ids'], [str(child.pk), str(teen.pk)])

    def test_apple_profile_installs_one_writable_family_caldav_account(self):
        other_user = get_user_model().objects.create_user('detail-sam')
        sam = Membership.objects.create(family=self.family, user=other_user, role=Membership.Role.CHILD, display_name='Sam')
        alex_only = self.make_event('Alex appointment', participant=self.membership)
        sam_only = self.make_event('Sam appointment', participant=sam)
        selected_private = self.make_event('Sam private selected', family_event=False, participant=sam)

        created = self.client.post(self.path, {'name': 'Family iPhones', 'detail_level': 'title'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['included_member_ids'], [])
        detail = self.path + created.data['id'] + '/'
        profile_response = self.client.get(detail + 'profile/')
        self.assertEqual(profile_response.status_code, 200)
        profile = plistlib.loads(profile_response.content)
        self.assertEqual(len(profile['PayloadContent']), 1)
        account = profile['PayloadContent'][0]
        self.assertEqual(account['PayloadType'], 'com.apple.caldav.account')
        self.assertEqual(account['PayloadDisplayName'], 'FamilyOS · Detail Family')
        self.assertEqual(account['CalDAVHostName'], 'calendar.example.test')
        self.assertEqual(account['CalDAVPort'], 443)
        self.assertTrue(account['CalDAVUseSSL'])
        self.assertEqual(account['CalDAVUsername'], created.data['username'])
        self.assertEqual(account['CalDAVPassword'], created.data['password'])
        self.assertNotIn('CalDAVPrincipalURL', account)
        self.assertNotIn('SubCalAccountHostName', account)

        auth = 'Basic ' + base64.b64encode(f"{created.data['username']}:{created.data['password']}".encode()).decode()
        calendar_path = f"/caldav/{created.data['id']}/home/family/"
        calendar_response = self.public.get(calendar_path, HTTP_AUTHORIZATION=auth)
        self.assertEqual(calendar_response.status_code, 200)
        titles = {str(event['SUMMARY']) for event in Calendar.from_ical(calendar_response.content).walk('VEVENT')}
        self.assertIn(self.event.title, titles)
        self.assertIn(alex_only.title, titles)
        self.assertNotIn(sam_only.title, titles)
        self.assertNotIn(selected_private.title, titles)

        scoped = self.client.patch(detail, {'included_member_ids': [str(sam.pk)]}, format='json')
        self.assertEqual(scoped.status_code, 200, scoped.data)
        self.assertEqual(scoped.data['included_member_ids'], [str(sam.pk)])
        scoped_titles = {str(event['SUMMARY']) for event in Calendar.from_ical(
            self.public.get(calendar_path, HTTP_AUTHORIZATION=auth).content
        ).walk('VEVENT')}
        self.assertIn(self.event.title, scoped_titles)
        self.assertIn(alex_only.title, scoped_titles)
        self.assertIn(sam_only.title, scoped_titles)
        self.assertNotIn(selected_private.title, scoped_titles)
