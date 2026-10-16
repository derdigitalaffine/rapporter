from datetime import datetime, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from icalendar import Calendar

from .caldav_models import CalDavConnection, CalDavEventBinding
from .caldav_secrets import encrypt_credentials, encrypt_value
from .caldav_sync import calendar_query_body, pull_remote, push_local
from .models import Family, FamilyEvent, Membership


EXPANDED_SERIES = b'''BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:weekly-1\r
DTSTART:20261020T080000Z\r
DTEND:20261020T090000Z\r
SUMMARY:Weekly remote\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:weekly-1\r
RECURRENCE-ID:20261027T080000Z\r
DTSTART:20261027T080000Z\r
DTEND:20261027T090000Z\r
SUMMARY:Weekly remote\r
END:VEVENT\r
END:VCALENDAR\r
'''


@override_settings(SECRET_KEY='caldav-recurrence-tests')
class CalDavRecurrenceAndScopeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('recurrence-owner')
        self.other = User.objects.create_user('recurrence-other')
        self.family = Family.objects.create(name='Recurring Family', slug='recurring-family', timezone='Europe/Berlin')
        self.member = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name='Alex')
        self.other_member = Membership.objects.create(family=self.family, user=self.other, role=Membership.Role.ADULT, display_name='Sam')
        self.connection = CalDavConnection.objects.create(
            scope=CalDavConnection.Scope.FAMILY,
            name='Apple · Alex',
            family=self.family,
            member=self.member,
            created_by=self.owner,
            access_mode=CalDavConnection.AccessMode.READ_WRITE,
            calendar_href_encrypted=encrypt_value('https://calendar.example.test/calendars/alex/'),
            credentials_encrypted=encrypt_credentials(
                server_url='https://calendar.example.test/dav',
                username='alex',
                password='secret',
            ),
        )
        self.start = datetime(2026, 10, 1, tzinfo=utc.utc)
        self.end = datetime(2026, 11, 1, tzinfo=utc.utc)

    def make_event(self, title, *, family_event, participant=None, hour=8):
        event = FamilyEvent.objects.create(
            family=self.family,
            type='calendar.event',
            title=title,
            starts_at=datetime(2026, 10, 20, hour, tzinfo=utc.utc),
            ends_at=datetime(2026, 10, 20, hour + 1, tzinfo=utc.utc),
            is_family_event=family_event,
        )
        if participant:
            event.participants.add(participant)
        return event

    def test_report_requests_rfc4791_server_expansion(self):
        body = calendar_query_body(self.start, self.end).decode()
        self.assertIn('<c:expand start="20261001T000000Z" end="20261101T000000Z"/>', body)
        self.assertIn('<c:time-range start="20261001T000000Z" end="20261101T000000Z"/>', body)

    @patch('family.caldav_sync.query_resources')
    def test_expanded_remote_series_projects_each_occurrence_read_only(self, query):
        href = 'https://calendar.example.test/calendars/alex/weekly.ics'
        query.return_value = [{'href': href, 'etag': '"weekly-v1"', 'data': EXPANDED_SERIES}]
        result = pull_remote(self.connection, self.start, self.end)
        self.assertEqual(result['pulled'], 2)
        self.assertEqual(result['recurring_instances'], 2)
        rows = list(FamilyEvent.objects.filter(source__config__caldav_connection=str(self.connection.id)).order_by('starts_at'))
        self.assertEqual([row.starts_at for row in rows], [
            datetime(2026, 10, 20, 8, tzinfo=utc.utc),
            datetime(2026, 10, 27, 8, tzinfo=utc.utc),
        ])
        self.assertTrue(all(row.payload.get('caldav_recurring_instance') is True for row in rows))
        bindings = list(CalDavEventBinding.objects.filter(connection=self.connection).order_by('remote_uid'))
        self.assertEqual(len(bindings), 2)
        self.assertEqual(len({binding.remote_uid for binding in bindings}), 2)
        self.assertTrue(all(binding.etag == '"weekly-v1"' for binding in bindings))

    @patch('family.caldav_sync.safe_request')
    def test_member_write_scope_excludes_events_selected_only_for_other_member(self, request):
        unassigned = self.make_event('Everyone', family_event=True, hour=8)
        mine = self.make_event('Alex family event', family_event=True, participant=self.member, hour=10)
        personal = self.make_event('Alex selected event', family_event=False, participant=self.member, hour=12)
        other = self.make_event('Sam only', family_event=True, participant=self.other_member, hour=14)

        def response(url, **kwargs):
            return url, 201, {'ETag': '"written"'}, b''
        request.side_effect = response

        result = push_local(self.connection, self.start, self.end)
        self.assertEqual(result['pushed'], 3)
        written_titles = set()
        for call in request.call_args_list:
            if call.kwargs.get('method') != 'PUT':
                continue
            calendar = Calendar.from_ical(call.kwargs['body'])
            written_titles.add(str(calendar.walk('VEVENT')[0]['SUMMARY']))
        self.assertEqual(written_titles, {unassigned.title, mine.title, personal.title})
        self.assertNotIn(other.title, written_titles)
