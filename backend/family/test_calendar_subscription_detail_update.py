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

    def test_apple_profile_installs_one_safe_calendar_per_active_family_member(self):
        other_user = get_user_model().objects.create_user('detail-sam')
        sam = Membership.objects.create(family=self.family, user=other_user, role=Membership.Role.CHILD, display_name='Sam')
        alex_only = self.make_event('Alex appointment', participant=self.membership)
        sam_only = self.make_event('Sam appointment', participant=sam)
        selected_private = self.make_event('Sam private selected', family_event=False, participant=sam)

        created = self.client.post(self.path, {'name': 'Family iPhones', 'detail_level': 'title'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        detail = self.path + created.data['id'] + '/'
        profile_response = self.client.get(detail + 'profile/')
        self.assertEqual(profile_response.status_code, 200)
        profile = plistlib.loads(profile_response.content)
        self.assertEqual(len(profile['PayloadContent']), 2)
        accounts = {item['PayloadDisplayName']: item for item in profile['PayloadContent']}
        self.assertEqual(set(accounts), {'FamilyOS · Alex', 'FamilyOS · Sam'})

        alex_url = accounts['FamilyOS · Alex']['SubCalAccountHostName']
        sam_url = accounts['FamilyOS · Sam']['SubCalAccountHostName']
        self.assertIn(f'/member/{self.membership.pk}.ics', alex_url)
        self.assertIn(f'/member/{sam.pk}.ics', sam_url)
        self.assertNotEqual(alex_url, sam_url)

        alex_calendar = Calendar.from_ical(self.public.get(alex_url.replace('https://calendar.example.test', '')).content)
        sam_calendar = Calendar.from_ical(self.public.get(sam_url.replace('https://calendar.example.test', '')).content)
        alex_titles = {str(event['SUMMARY']) for event in alex_calendar.walk('VEVENT')}
        sam_titles = {str(event['SUMMARY']) for event in sam_calendar.walk('VEVENT')}
        self.assertIn(self.event.title, alex_titles)
        self.assertIn(self.event.title, sam_titles)
        self.assertIn(alex_only.title, alex_titles)
        self.assertNotIn(alex_only.title, sam_titles)
        self.assertIn(sam_only.title, sam_titles)
        self.assertNotIn(sam_only.title, alex_titles)
        self.assertNotIn(selected_private.title, alex_titles)
        self.assertNotIn(selected_private.title, sam_titles)
