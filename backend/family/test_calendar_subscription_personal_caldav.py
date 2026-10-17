import base64
from datetime import datetime, timedelta, timezone as utc

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from icalendar import Calendar, Event, vCalAddress
from rest_framework.test import APIClient

from .models import Family, FamilyEvent, Membership


@override_settings(APP_URL='https://calendar.example.test', AUTH_ABUSE_HMAC_KEY='calendar-personal-caldav-tests', DEBUG=True)
class CalendarSubscriptionPersonalCalDavTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner_user = User.objects.create_user('personal-caldav-owner', password='calendar-test-password')
        self.child_user = User.objects.create_user('personal-caldav-child')
        self.other_child_user = User.objects.create_user('personal-caldav-other-child')
        self.family = Family.objects.create(name='Personal calendar family', slug='personal-calendar-family', timezone='Europe/Berlin')
        self.owner = Membership.objects.create(
            family=self.family, user=self.owner_user, role=Membership.Role.OWNER, display_name='Alex',
        )
        self.child = Membership.objects.create(
            family=self.family, user=self.child_user, role=Membership.Role.CHILD, display_name='Indira',
        )
        self.other_child = Membership.objects.create(
            family=self.family, user=self.other_child_user, role=Membership.Role.CHILD, display_name='Robin',
        )
        self.start = datetime(2026, 10, 20, 15, 0, tzinfo=utc.utc)

        self.client = APIClient()
        login = self.client.post(
            '/api/auth/login/',
            {'username': self.owner_user.username, 'password': 'calendar-test-password'},
            format='json',
        )
        self.assertEqual(login.status_code, 200, login.data)
        created = self.client.post(
            f'/api/calendar-subscriptions/{self.family.pk}/',
            {'name': 'Owner iPhone', 'detail_level': 'title', 'included_member_ids': [str(self.child.pk)]},
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.grant = created.data
        self.public = APIClient()
        self.auth = 'Basic ' + base64.b64encode(
            f"{self.grant['username']}:{self.grant['password']}".encode()
        ).decode()
        self.home = f"/caldav/{self.grant['id']}/home/family/"
        self.principals = f"/caldav/{self.grant['id']}/principals/"

    def dav(self, method='GET', path=None, body=b'', content_type='application/xml', **headers):
        return self.public.generic(
            method,
            path or self.home,
            body,
            content_type=content_type,
            HTTP_AUTHORIZATION=self.auth,
            **headers,
        )

    def personal_event(self, title, member, offset=0):
        event = FamilyEvent.objects.create(
            family=self.family,
            type='calendar.event',
            title=title,
            starts_at=self.start + timedelta(days=offset),
            ends_at=self.start + timedelta(days=offset, hours=1),
            is_family_event=False,
        )
        event.participants.add(member)
        return event

    def event_body(self, event, attendees=()):
        calendar = Calendar(); calendar.add('version', '2.0'); calendar.add('prodid', '-//FamilyOS test//EN')
        component = Event(); component.add('uid', f'{event.pk}@familyos'); component.add('summary', event.title)
        component.add('dtstart', event.starts_at); component.add('dtend', event.ends_at)
        organizer = vCalAddress(f'mailto:{self.owner.pk}@members.familyos.invalid')
        component.add('ORGANIZER', organizer, encode=0)
        for member in attendees:
            attendee = vCalAddress(f'mailto:{member.pk}@members.familyos.invalid')
            attendee.params['CN'] = member.display_name
            component.add('ATTENDEE', attendee, encode=0)
        calendar.add_component(component)
        return calendar.to_ical()

    @staticmethod
    def titles(response):
        return {str(event['SUMMARY']) for event in Calendar.from_ical(response.content).walk('VEVENT')}

    def test_caldav_exports_personal_owner_and_selected_child_events_only(self):
        self.personal_event('Owner personal', self.owner)
        self.personal_event('Selected child personal', self.child, offset=1)
        self.personal_event('Unselected child personal', self.other_child, offset=2)

        response = self.dav()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.titles(response), {'Owner personal', 'Selected child personal'})

    def test_caldav_can_add_participant_to_personal_event_without_promoting_it(self):
        event = self.personal_event('Owner personal', self.owner)
        path = self.home + str(event.pk) + '.ics'
        fetched = self.dav(path=path)
        self.assertEqual(fetched.status_code, 200)

        updated = self.dav(
            'PUT',
            path=path,
            body=self.event_body(event, attendees=[self.child]),
            content_type='text/calendar',
            HTTP_IF_SCHEDULE_TAG_MATCH=fetched['Schedule-Tag'],
        )
        self.assertEqual(updated.status_code, 204)
        event.refresh_from_db()
        self.assertFalse(event.is_family_event)
        self.assertEqual(set(event.participants.values_list('pk', flat=True)), {self.owner.pk, self.child.pk})

        returned = self.dav(path=path)
        component = Calendar.from_ical(returned.content).walk('VEVENT')[0]
        attendees = component['ATTENDEE'] if isinstance(component['ATTENDEE'], list) else [component['ATTENDEE']]
        self.assertEqual(
            {str(value) for value in attendees},
            {
                f'mailto:{self.owner.pk}@members.familyos.invalid',
                f'mailto:{self.child.pk}@members.familyos.invalid',
            },
        )

        deleted = self.dav('DELETE', path=path, HTTP_IF_MATCH=returned['ETag'])
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(FamilyEvent.objects.filter(pk=event.pk).exists())

    def test_principal_search_accepts_multiple_properties_in_one_search(self):
        body = '''<D:principal-property-search xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
          <D:property-search>
            <D:prop><D:displayname/><C:calendar-user-type/></D:prop>
            <D:match>in</D:match>
          </D:property-search>
          <D:prop><D:displayname/><C:calendar-user-address-set/></D:prop>
        </D:principal-property-search>'''
        response = self.dav('REPORT', path=self.principals, body=body)
        self.assertEqual(response.status_code, 207)
        self.assertIn((self.principals + str(self.child.pk) + '/').encode(), response.content)
        self.assertIn(b'Indira', response.content)

    def test_principal_search_matches_advertised_principal_calendar_address(self):
        body = '''<D:principal-property-search xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
          <D:property-search>
            <D:prop><C:calendar-user-address-set/></D:prop>
            <D:match>principals</D:match>
          </D:property-search>
          <D:prop><D:displayname/><C:calendar-user-address-set/></D:prop>
        </D:principal-property-search>'''
        response = self.dav('REPORT', path=self.principals, body=body)
        self.assertEqual(response.status_code, 207)
        self.assertIn((self.principals + str(self.child.pk) + '/').encode(), response.content)
