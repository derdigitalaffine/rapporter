from datetime import datetime, timezone as utc

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from .caldav_discovery import CalDavDiscoveryError
from .caldav_models import CalDavConnection
from .caldav_secrets import encrypt_credentials, encrypt_value
from .caldav_sync import query_resources
from .models import Family, Membership


@override_settings(SECRET_KEY='caldav-origin-tests')
class CalDavResourceOriginTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user('origin-owner')
        family = Family.objects.create(name='Origin Family', slug='origin-family')
        member = Membership.objects.create(family=family, user=user, role=Membership.Role.OWNER)
        self.connection = CalDavConnection.objects.create(
            scope=CalDavConnection.Scope.FAMILY,
            name='Origin calendar',
            family=family,
            member=member,
            created_by=user,
            calendar_href_encrypted=encrypt_value('https://calendar.example.test/calendars/alice/'),
            credentials_encrypted=encrypt_credentials(
                server_url='https://calendar.example.test/dav',
                username='alice',
                password='secret',
            ),
        )
        self.start = datetime(2026, 10, 1, tzinfo=utc.utc)
        self.end = datetime(2026, 11, 1, tzinfo=utc.utc)

    def test_report_cannot_redirect_resource_credentials_to_another_origin(self):
        def requester(url, **kwargs):
            payload = b'''<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response><d:href>https://attacker.example/steal.ics</d:href><d:propstat><d:prop><d:getetag>"e1"</d:getetag><c:calendar-data>BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR</c:calendar-data></d:prop></d:propstat></d:response></d:multistatus>'''
            return url, 207, {}, payload

        with self.assertRaisesMessage(CalDavDiscoveryError, 'caldav_resource_origin_rejected'):
            query_resources(self.connection, self.start, self.end, requester=requester)

    def test_relative_resource_href_stays_on_selected_origin(self):
        def requester(url, **kwargs):
            payload = b'''<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response><d:href>/calendars/alice/event.ics</d:href><d:propstat><d:prop><d:getetag>"e1"</d:getetag><c:calendar-data>BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR</c:calendar-data></d:prop></d:propstat></d:response></d:multistatus>'''
            return url, 207, {}, payload

        rows = query_resources(self.connection, self.start, self.end, requester=requester)
        self.assertEqual(rows[0]['href'], 'https://calendar.example.test/calendars/alice/event.ics')
