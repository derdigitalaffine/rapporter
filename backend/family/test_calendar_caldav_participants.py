import base64
from datetime import datetime, timedelta, timezone as utc
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from icalendar import Calendar, Event, vCalAddress
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership


@override_settings(APP_URL='https://calendar.example.test', AUTH_ABUSE_HMAC_KEY='calendar-tests', DEBUG=True)
class CalDavFamilyParticipantTests(TestCase):
    def setUp(self):
        self.owner_user = get_user_model().objects.create_user('calendar-owner', password='calendar-test-password')
        self.child_user = get_user_model().objects.create_user('calendar-child')
        self.assertEqual(self.child_user.email, '')
        self.family = Family.objects.create(name='Family', slug='calendar-participant-family', timezone='Europe/Berlin')
        self.owner = Membership.objects.create(family=self.family, user=self.owner_user, role='owner', display_name='Alex')
        self.child = Membership.objects.create(family=self.family, user=self.child_user, role='child', display_name='Emma')
        self.client = APIClient()
        login = self.client.post('/api/auth/login/', {'username': self.owner_user.username, 'password': 'calendar-test-password'}, format='json')
        self.assertEqual(login.status_code, 200, login.data)
        created = self.client.post(
            f'/api/calendar-subscriptions/{self.family.pk}/',
            {'name': 'iPhone', 'detail_level': 'title'},
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.grant = created.data
        self.public = APIClient()
        self.auth = 'Basic ' + base64.b64encode(f"{self.grant['username']}:{self.grant['password']}".encode()).decode()
        self.home = f"/caldav/{self.grant['id']}/home/family/"
        self.principals = f"/caldav/{self.grant['id']}/principals/"
        self.start = datetime(2026, 10, 20, 15, 0, tzinfo=utc.utc)

    def dav(self, method='PROPFIND', path=None, body='', content_type='application/xml', **headers):
        return self.public.generic(
            method,
            path or self.home,
            body,
            content_type=content_type,
            HTTP_AUTHORIZATION=self.auth,
            **headers,
        )

    def event_body(self, event_id, title='Family event', attendees=()):
        calendar = Calendar(); calendar.add('version', '2.0'); calendar.add('prodid', '-//FamilyOS test//EN')
        event = Event(); event.add('uid', f'{event_id}@iphone'); event.add('summary', title)
        event.add('dtstart', self.start); event.add('dtend', self.start + timedelta(hours=1))
        for address, label in attendees:
            attendee = vCalAddress(address); attendee.params['CN'] = label
            event.add('ATTENDEE', attendee, encode=0)
        calendar.add_component(event)
        return calendar.to_ical()

    def test_child_without_email_is_searchable_as_caldav_principal(self):
        principal = f"/caldav/{self.grant['id']}/principal/"
        propfind = self.dav(
            path=principal,
            body='<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:principal-collection-set/><c:calendar-user-address-set/></d:prop></d:propfind>',
            HTTP_DEPTH='0',
        )
        self.assertEqual(propfind.status_code, 207)
        self.assertIn(self.principals.encode(), propfind.content)
        self.assertIn(f'mailto:{self.owner.pk}@members.familyos.invalid'.encode(), propfind.content)

        body = '''<d:principal-property-search xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
          <d:property-search><d:prop><d:displayname/></d:prop><d:match>Emma</d:match></d:property-search>
          <d:prop><d:displayname/><c:calendar-user-address-set/><c:calendar-user-type/></d:prop>
        </d:principal-property-search>'''
        result = self.dav('REPORT', path=self.principals, body=body)
        self.assertEqual(result.status_code, 207)
        self.assertIn(f'{self.principals}{self.child.pk}/'.encode(), result.content)
        self.assertIn(b'Emma', result.content)
        self.assertIn(f'mailto:{self.child.pk}@members.familyos.invalid'.encode(), result.content)
        self.assertIn(f'urn:uuid:{self.child.pk}'.encode(), result.content)
        self.assertIn(b'INDIVIDUAL', result.content)
        self.assertNotIn(b'calendar-schedule', result.get('DAV', '').encode())
        self.assertNotIn(b'schedule-inbox-URL', result.content)
        self.assertNotIn(b'schedule-outbox-URL', result.content)

    def test_existing_family_participant_is_exported_without_public_ics_leak(self):
        event = FamilyEvent.objects.create(
            family=self.family,
            type='calendar.event',
            title='Dentist',
            starts_at=self.start,
            ends_at=self.start + timedelta(hours=1),
            is_family_event=True,
        )
        event.participants.add(self.child)
        response = self.dav('GET', path=self.home + str(event.pk) + '.ics')
        self.assertEqual(response.status_code, 200)
        component = Calendar.from_ical(response.content).walk('VEVENT')[0]
        attendee = component['ATTENDEE']
        self.assertEqual(str(attendee), f'mailto:{self.child.pk}@members.familyos.invalid')
        self.assertEqual(str(attendee.params['CN']), 'Emma')
        self.assertEqual(str(attendee.params['SCHEDULE-AGENT']), 'NONE')

        feed_path = self.grant['subscription_url'].replace('https://calendar.example.test', '')
        public_feed = self.public.get(feed_path)
        self.assertEqual(public_feed.status_code, 200)
        self.assertNotIn(b'ATTENDEE', public_feed.content)
        self.assertNotIn(str(self.child.pk).encode(), public_feed.content)

    def test_put_maps_family_attendees_bidirectionally_and_rejects_outsiders(self):
        event_id = uuid4(); path = self.home + str(event_id) + '.ics'
        address = f'mailto:{self.child.pk}@members.familyos.invalid'
        created = self.dav(
            'PUT', path=path,
            body=self.event_body(event_id, attendees=[(address, 'Emma')]),
            content_type='text/calendar', HTTP_IF_NONE_MATCH='*',
        )
        self.assertEqual(created.status_code, 201)
        stored = FamilyEvent.objects.get(pk=event_id)
        self.assertEqual(list(stored.participants.values_list('pk', flat=True)), [self.child.pk])

        fetched = self.dav('GET', path=path)
        component = Calendar.from_ical(fetched.content).walk('VEVENT')[0]
        self.assertEqual(str(component['ATTENDEE']), address)

        removed = self.dav(
            'PUT', path=path,
            body=self.event_body(event_id, title='No assignee'),
            content_type='text/calendar', HTTP_IF_MATCH=created['ETag'],
        )
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(FamilyEvent.objects.get(pk=event_id).participants.exists())

        principal_event_id = uuid4(); principal_path = self.home + str(principal_event_id) + '.ics'
        principal_address = f'{self.principals}{self.child.pk}/'
        via_principal = self.dav(
            'PUT', path=principal_path,
            body=self.event_body(principal_event_id, attendees=[(principal_address, 'Emma')]),
            content_type='text/calendar', HTTP_IF_NONE_MATCH='*',
        )
        self.assertEqual(via_principal.status_code, 201)
        self.assertTrue(FamilyEvent.objects.get(pk=principal_event_id).participants.filter(pk=self.child.pk).exists())

        outsider_id = uuid4(); outsider_path = self.home + str(outsider_id) + '.ics'
        rejected = self.dav(
            'PUT', path=outsider_path,
            body=self.event_body(outsider_id, attendees=[('mailto:outsider@example.com', 'Outsider')]),
            content_type='text/calendar', HTTP_IF_NONE_MATCH='*',
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertFalse(FamilyEvent.objects.filter(pk=outsider_id).exists())
