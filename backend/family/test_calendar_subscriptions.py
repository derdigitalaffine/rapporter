import base64
import io
import logging
import plistlib
from datetime import datetime, timedelta, timezone as utc
from unittest.mock import patch
from uuid import uuid4
from xml.etree import ElementTree as ET
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from icalendar import Calendar, Event
from auth_sessions.models import AuthSession
from telemetry.models import AuditEvent
from .models import Family, Membership, FamilyEvent, IntegrationSource
from .calendar_subscription_models import CalendarSubscription
from .calendar_subscription_privacy import CalendarSecretFilter, redact
from .calendar_subscription_ics import CalendarCapacityError, calendar_bytes, overlaps, projection


@override_settings(APP_URL='https://calendar.example.test', AUTH_ABUSE_HMAC_KEY='calendar-tests', DEBUG=True)
class CalendarSubscriptionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('subscriber', password='calendar-test-password')
        self.family = Family.objects.create(name='Family <&>', slug='subscribers', timezone='Europe/Berlin')
        self.membership = Membership.objects.create(family=self.family, user=self.user, role='owner')
        self.client = APIClient()
        login = self.client.post('/api/auth/login/', {'username': self.user.username, 'password': 'calendar-test-password'}, format='json')
        self.assertEqual(login.status_code, 200, login.data)
        self.path = f'/api/calendar-subscriptions/{self.family.pk}/'
        self.public = APIClient()
        self.start = datetime(2026, 3, 22, 9, tzinfo=utc.utc)
        self.event = self.make_event('Shared, family; ü\nSecond line', payload={'location': 'Never exported', 'description': 'Private note'})
        self.event.participants.add(self.membership)

    def make_event(self, title, **kwargs):
        values = dict(family=self.family, type='calendar.event', title=title, starts_at=self.start, ends_at=self.start + timedelta(hours=1), is_family_event=True)
        values.update(kwargs)
        return FamilyEvent.objects.create(**values)

    def create(self, detail_level='title'):
        response = self.client.post(self.path, {'name': 'My iPhone', 'detail_level': detail_level}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn('no-store', response['Cache-Control'])
        self.grant = response.data
        self.detail = self.path + self.grant['id'] + '/'
        self.feed = self.grant['subscription_url'].replace('https://calendar.example.test', '')
        self.home = f"/caldav/{self.grant['id']}/home/family/"
        self.auth = 'Basic ' + base64.b64encode(f"{self.grant['username']}:{self.grant['password']}".encode()).decode()
        return response

    def dav(self, method='PROPFIND', path=None, body='', content_type='application/xml', **headers):
        return self.public.generic(method, path or self.home, body, content_type=content_type, HTTP_AUTHORIZATION=self.auth, **headers)

    def test_permanent_secret_is_encrypted_not_in_lists_and_feed_is_current(self):
        self.create()
        stored = CalendarSubscription.objects.get(pk=self.grant['id'])
        self.assertNotIn(self.grant['password'], stored.credentials_encrypted)
        self.assertEqual(len(stored.token_digest), 64)
        listing = self.client.get(self.path)
        self.assertNotIn(self.grant['password'], str(listing.data))
        first = self.public.get(self.feed); self.assertEqual(first.status_code, 200)
        self.assertIn('no-store', first['Cache-Control'])
        self.assertEqual(first['Referrer-Policy'], 'no-referrer')
        self.assertEqual(self.public.head(self.feed).content, b'')
        self.assertEqual(self.public.get(self.feed, HTTP_IF_NONE_MATCH=first['ETag']).status_code, 304)
        self.event.title = 'Changed family event'; self.event.save()
        updated = self.public.get(self.feed)
        self.assertNotEqual(updated['ETag'], first['ETag'])
        self.assertIn(b'Changed family event', updated.content)
        self.assertEqual(self.client.post(self.detail + 'reveal/').data['subscription_url'], self.grant['subscription_url'])
        self.assertEqual(self.public.post(self.feed).status_code, 405)

    def test_private_selected_external_health_and_other_families_never_exported(self):
        self.make_event('Private', is_family_event=False)
        selected = self.make_event('Selected', is_family_event=False); selected.participants.add(self.membership)
        source = IntegrationSource.objects.create(family=self.family, kind='ics', name='External')
        self.make_event('Imported', source=source)
        self.make_event('Orphaned import', external_id='external-123')
        self.make_event('Protected', type='health.appointment')
        other = Family.objects.create(name='Other', slug='other')
        alien = self.make_event('Alien', family=other)
        self.create()
        data = self.public.get(self.feed).content.decode()
        for secret in ('Private', 'Selected', 'Imported', 'Orphaned import', 'Protected', 'Alien', 'Never exported', 'Private note'):
            self.assertNotIn(secret, data)
        calendar = Calendar.from_ical(data)
        events = calendar.walk('VEVENT')
        self.assertEqual(len(events), 1)
        self.assertEqual(str(events[0]['SUMMARY']), self.event.title)
        self.assertEqual(self.dav('GET', self.home + str(alien.pk) + '.ics').status_code, 404)

    def test_detail_level_is_enforced_server_side(self):
        self.create('availability')
        event = Calendar.from_ical(self.public.get(self.feed).content).walk('VEVENT')[0]
        self.assertEqual(str(event['SUMMARY']), 'Belegt')
        self.assertNotIn('LOCATION', event)
        self.assertNotIn('DESCRIPTION', event)
        listing = self.client.get(self.path).data['subscriptions']
        self.assertEqual(listing[0]['detail_level'], 'availability')

        self.create('full')
        event = Calendar.from_ical(self.public.get(self.feed).content).walk('VEVENT')[0]
        self.assertEqual(str(event['SUMMARY']), self.event.title)
        self.assertEqual(str(event['LOCATION']), 'Never exported')
        self.assertNotIn('DESCRIPTION', event)

    def test_revoke_and_rotation_invalidate_old_feed_and_profile_credentials(self):
        self.create()
        new = self.client.post(self.detail + 'rotate/'); self.assertEqual(new.status_code, 200)
        self.assertNotEqual(new.data['password'], self.grant['password'])
        self.assertEqual(self.public.get(self.feed).status_code, 404)
        self.assertEqual(self.dav('GET').status_code, 401)
        new_feed = new.data['subscription_url'].replace('https://calendar.example.test', '')
        self.assertEqual(self.public.get(new_feed).status_code, 200)
        self.assertEqual(self.client.delete(self.detail).status_code, 204)
        self.assertEqual(self.public.get(new_feed).status_code, 404)
        self.assertEqual(self.client.get(self.detail + 'profile/').status_code, 404)
        self.assertEqual(CalendarSubscription.objects.get(pk=self.grant['id']).credentials_encrypted, '')

    def test_removed_member_demoted_creator_disabled_user_and_suspended_family_deny_existing_grant(self):
        self.create()
        self.membership.role = 'teen'; self.membership.save()
        self.assertEqual(self.public.get(self.feed).status_code, 404)
        self.assertEqual(self.dav('GET').status_code, 401)
        self.membership.role = 'adult'; self.membership.save()
        self.assertEqual(self.public.get(self.feed).status_code, 200)
        self.user.is_active = False; self.user.save()
        self.assertEqual(self.public.get(self.feed).status_code, 404)
        self.user.is_active = True; self.user.save()
        self.family.status = 'suspended'; self.family.save()
        self.assertEqual(self.public.get(self.feed).status_code, 404)
        self.family.status = 'active'; self.family.save(); self.membership.delete()
        self.assertEqual(self.public.get(self.feed).status_code, 404)

    def test_fresh_reauth_and_creator_only_management(self):
        self.create()
        AuthSession.objects.filter(user=self.user).update(last_reauthenticated_at=timezone.now() - timedelta(hours=1))
        for suffix in ('reveal/', 'rotate/'):
            result = self.client.post(self.detail + suffix)
            self.assertEqual(result.status_code, 403); self.assertEqual(result.data['code'], 'reauth_required')
            self.assertIn('no-store', result['Cache-Control'])
        self.assertEqual(self.client.get(self.detail + 'profile/').status_code, 403)
        self.assertEqual(self.client.post(self.path, {'name': 'New'}, format='json').status_code, 403)
        other = get_user_model().objects.create_user('other')
        Membership.objects.create(user=other, family=self.family, role='adult')
        client = APIClient(); client.force_authenticate(other)
        self.assertEqual(client.get(self.path).data['subscriptions'], [])
        self.assertEqual(client.delete(self.detail).status_code, 404)
        self.assertEqual(self.client.delete(self.detail).status_code, 204)

    def test_cross_family_management_role_and_no_normal_account_password_for_dav(self):
        self.create()
        other = Family.objects.create(name='Other', slug='other')
        self.assertIn(self.client.get(f'/api/calendar-subscriptions/{other.pk}/').status_code, (403, 404))
        self.membership.role = 'child'; self.membership.save()
        self.assertEqual(self.client.get(self.path).status_code, 403)
        wrong = 'Basic ' + base64.b64encode(b'subscriber:calendar-test-password').decode()
        self.assertEqual(self.public.generic('PROPFIND', '/caldav/', HTTP_AUTHORIZATION=wrong, HTTP_DEPTH='0').status_code, 401)

    def test_profile_uses_native_apple_caldav_payload(self):
        self.create()
        response = self.client.get(self.detail + 'profile/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/x-apple-aspen-config')
        profile = plistlib.loads(response.content)
        self.assertEqual(profile['PayloadType'], 'Configuration')
        self.assertEqual(len(profile['PayloadContent']), 1)
        account = profile['PayloadContent'][0]
        self.assertEqual(account['PayloadType'], 'com.apple.caldav.account')
        self.assertEqual(account['CalDAVHostName'], 'calendar.example.test')
        self.assertEqual(account['CalDAVPort'], 443)
        self.assertTrue(account['CalDAVUseSSL'])
        self.assertNotIn('CalDAVPrincipalURL', account)
        self.assertEqual(account['CalDAVUsername'], self.grant['username'])
        self.assertEqual(account['CalDAVPassword'], self.grant['password'])
        self.assertNotIn('SubCalAccountHostName', account)
        self.assertNotIn('calendar-test-password', str(profile))
        self.assertEqual(self.public.get(self.feed).status_code, 200)
        self.assertEqual(AuditEvent.objects.filter(event_key='calendar.subscription.profile').count(), 1)
        audit_data = str(list(AuditEvent.objects.values('metadata', 'target_id')))
        self.assertNotIn(self.grant['password'], audit_data)

    @override_settings(APP_URL='http://untrusted.example')
    def test_insecure_canonical_origin_refuses_create_without_host_fallback(self):
        response = self.client.post(self.path, {'name': 'Device'}, format='json', HTTP_HOST='attacker.test')
        self.assertIn(response.status_code, (400, 403))
        self.assertFalse(CalendarSubscription.objects.exists())

    def test_dav_discovery_etag_report_query_and_multiget(self):
        self.create()
        self.assertEqual(self.public.get('/.well-known/caldav')['Location'], '/caldav/')
        root = self.dav(path='/caldav/', body='<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:current-user-principal/><c:calendar-home-set/><d:unknown/></d:prop></d:propfind>', HTTP_DEPTH='0')
        self.assertEqual(root.status_code, 207)
        self.assertIn(self.grant['id'].encode(), root.content); self.assertIn(b'404 Not Found', root.content)
        self.assertEqual(self.dav(HTTP_DEPTH='infinity').status_code, 403)
        listing = self.dav(HTTP_DEPTH='1'); self.assertEqual(listing.status_code, 207)
        self.assertIn(str(self.event.pk).encode(), listing.content)
        self.assertIn(b'<d:write', listing.content)
        self.assertNotIn(b'sync-token', listing.content)
        query = '<c:calendar-query xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:d="DAV:"><d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range start="20260322T000000Z" end="20260323T000000Z"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>'
        report = self.dav('REPORT', body=query); self.assertEqual(report.status_code, 207)
        xml = ET.fromstring(report.content); data = xml.find('.//{urn:ietf:params:xml:ns:caldav}calendar-data').text
        self.assertEqual(str(Calendar.from_ical(data).walk('VEVENT')[0]['UID']), f'{self.event.pk}@familyos')
        href = self.home + str(self.event.pk) + '.ics'
        body = f'<c:calendar-multiget xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:d="DAV:"><d:prop><c:calendar-data/></d:prop><d:href>{href}</d:href></c:calendar-multiget>'
        self.assertEqual(self.dav('REPORT', body=body).status_code, 207)
        self.assertEqual(self.dav('REPORT', body=body.replace(href, '/caldav/other/home/family/stolen.ics')).status_code, 403)
        for method in ('MKCALENDAR', 'PROPPATCH', 'ACL'):
            self.assertEqual(self.dav(method).status_code, 403)
        self.assertEqual(self.dav('PUT').status_code, 403)
        self.assertEqual(self.dav('DELETE').status_code, 403)

    def test_caldav_query_returns_family_events_across_days(self):
        second = self.make_event(
            'Tomorrow',
            starts_at=self.start + timedelta(days=1),
            ends_at=self.start + timedelta(days=1, hours=1),
        )
        second.participants.add(self.membership)
        self.create()
        query = '<c:calendar-query xmlns:c="urn:ietf:params:xml:ns:caldav"><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range start="20260322T000000Z" end="20260324T000000Z"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>'
        response = self.dav('REPORT', body=query)
        self.assertEqual(response.status_code, 207)
        self.assertIn(str(self.event.pk).encode(), response.content)
        self.assertIn(str(second.pk).encode(), response.content)

    def test_dav_put_update_delete_roundtrip_with_etag(self):
        self.create()
        event_id = uuid4()
        path = self.home + str(event_id) + '.ics'

        def body(summary, start):
            calendar = Calendar(); calendar.add('version', '2.0'); calendar.add('prodid', '-//iPhone test//EN')
            component = Event(); component.add('uid', 'iphone-stable-uid@example.test'); component.add('summary', summary)
            component.add('dtstart', start); component.add('dtend', start + timedelta(hours=1))
            calendar.add_component(component)
            return calendar.to_ical()

        created = self.dav('PUT', path=path, body=body('Created on iPhone', self.start + timedelta(days=2)),
                           content_type='text/calendar', HTTP_IF_NONE_MATCH='*')
        self.assertEqual(created.status_code, 201)
        self.assertIn('ETag', created)
        stored = FamilyEvent.objects.get(pk=event_id)
        self.assertEqual(stored.title, 'Created on iPhone')
        self.assertTrue(stored.is_family_event)
        self.assertEqual(stored.payload['caldav_uid'], 'iphone-stable-uid@example.test')
        self.assertEqual(list(stored.participants.values_list('pk', flat=True)), [self.membership.pk])
        fetched = self.dav('GET', path=path)
        parsed = Calendar.from_ical(fetched.content).walk('VEVENT')[0]
        self.assertEqual(str(parsed['UID']), 'iphone-stable-uid@example.test')

        updated = self.dav('PUT', path=path, body=body('Changed on iPhone', self.start + timedelta(days=3)),
                           content_type='text/calendar', HTTP_IF_MATCH=created['ETag'])
        self.assertEqual(updated.status_code, 204)
        self.assertEqual(FamilyEvent.objects.get(pk=event_id).title, 'Changed on iPhone')
        stale = self.dav('PUT', path=path, body=body('Stale', self.start + timedelta(days=4)),
                         content_type='text/calendar', HTTP_IF_MATCH=created['ETag'])
        self.assertEqual(stale.status_code, 412)
        deleted = self.dav('DELETE', path=path, HTTP_IF_MATCH=updated['ETag'])
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(FamilyEvent.objects.filter(pk=event_id).exists())

    def test_bounded_xml_and_unsupported_filters_fail_closed(self):
        self.create()
        for body in ('<!DOCTYPE x [<!ENTITY a "secret">]><x>&a;</x>', '<x>' * 20 + '</x>' * 20, '<x>' + 'a' * 65536 + '</x>'):
            self.assertEqual(self.dav('REPORT', body=body).status_code, 400)
        body = '<c:calendar-query xmlns:c="urn:ietf:params:xml:ns:caldav"><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:prop-filter name="SUMMARY"/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>'
        self.assertEqual(self.dav('REPORT', body=body).status_code, 400)
        with patch('family.calendar_subscription_dav.shared_events', side_effect=CalendarCapacityError):
            self.assertEqual(self.public.get(self.feed).status_code, 507)

    def test_ics_all_day_timezone_recurrence_stable_uid_and_quarterly_core(self):
        self.event.payload = {'recurrence': {'frequency': 'weekly', 'interval': 1, 'weekdays': ['SU']}}
        self.event.save()
        self.create()
        data = Calendar.from_ical(self.public.get(self.feed).content)
        component = data.walk('VEVENT')[0]
        self.assertEqual(str(component['RRULE'].to_ical().decode()), 'FREQ=WEEKLY;INTERVAL=1;BYDAY=SU')
        self.assertTrue(data.walk('VTIMEZONE'))
        self.assertTrue(overlaps(self.event, datetime(2026, 3, 29, 8, tzinfo=utc.utc), datetime(2026, 3, 29, 9, tzinfo=utc.utc)))
        self.assertFalse(overlaps(self.event, datetime(2026, 3, 29, 9, tzinfo=utc.utc), datetime(2026, 3, 29, 10, tzinfo=utc.utc)))
        all_day = self.make_event('All day', payload={'all_day': True, 'date_start': '2026-03-22', 'date_end_exclusive': '2026-03-24'})
        component = Calendar.from_ical(calendar_bytes(self.family, [all_day])).walk('VEVENT')[0]
        self.assertEqual(component.decoded('dtend').isoformat(), '2026-03-24')
        self.event.payload = {'recurrence': {'frequency': 'quarterly', 'interval': 1, 'nth_weekdays': [{'weekday': 'MO', 'ordinal': -1}]}}
        self.event.save()
        quarter = Calendar.from_ical(calendar_bytes(self.family, [self.event])).walk('VEVENT')[0]
        self.assertIn('RDATE', quarter); self.assertNotIn('RRULE', quarter)
        self.assertTrue(projection(self.event, self.start.date(), self.start.date() + timedelta(days=365)))

    def test_secret_url_redacted_in_django_and_daphne_access_logs(self):
        self.create()
        token = self.grant['password']
        self.assertNotIn(token, redact(self.feed))
        record = logging.LogRecord('django.request', logging.ERROR, '', 1, 'Not found: %s', (self.feed,), None)
        CalendarSecretFilter().filter(record)
        self.assertNotIn(token, record.getMessage())
        from config.serve import RedactingServer
        captured = []
        with patch('daphne.server.Server.__init__', return_value=None) as initialize:
            RedactingServer(action_logger=lambda protocol, action, details: captured.append(details))
        initialize.call_args.kwargs['action_logger']('http', 'complete', {'path': self.feed, 'status': 200})
        self.assertNotIn(token, captured[0]['path'])

    def test_ordinal_recurrence_has_no_phantom_anchor_occurrence(self):
        self.event.starts_at = datetime(2026, 10, 14, 8, tzinfo=utc.utc)
        self.event.ends_at = self.event.starts_at + timedelta(hours=1)
        self.event.payload = {'recurrence': {'frequency': 'monthly', 'interval': 1, 'nth_weekdays': [{'weekday': 'MO', 'ordinal': 1}]}}
        self.event.save()
        component = Calendar.from_ical(calendar_bytes(self.family, [self.event])).walk('VEVENT')[0]
        self.assertEqual(component.decoded('dtstart').date().isoformat(), '2026-11-02')
        self.assertEqual(component.decoded('dtend').hour, 11)

    def test_rfc_open_ended_time_ranges_work_for_native_calendar_clients(self):
        self.create()
        def query(bounds):
            return self.dav('REPORT', body=f'<c:calendar-query xmlns:c="urn:ietf:params:xml:ns:caldav"><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"><c:time-range {bounds}/></c:comp-filter></c:comp-filter></c:filter></c:calendar-query>')
        before = query('end="20260323T000000Z"')
        self.assertEqual(before.status_code, 207); self.assertIn(str(self.event.pk).encode(), before.content)
        after = query('start="20260401T000000Z"')
        self.assertEqual(after.status_code, 207); self.assertNotIn(str(self.event.pk).encode(), after.content)
        self.event.payload = {'recurrence': 'weekly'}; self.event.save()
        recurring = query('start="20260401T000000Z"')
        self.assertEqual(recurring.status_code, 207); self.assertIn(str(self.event.pk).encode(), recurring.content)

    def test_production_requires_https_even_for_existing_bearer_links(self):
        self.create()
        with override_settings(DEBUG=False):
            self.assertEqual(self.public.get(self.feed).status_code, 403)
            self.assertEqual(self.public.get(self.feed, secure=True).status_code, 200)
            self.assertEqual(self.client.post(self.detail + 'reveal/').status_code, 403)
            self.assertEqual(self.client.post(self.detail + 'reveal/', secure=True).status_code, 200)

    def test_member_feed_and_subscription_are_participant_scoped(self):
        other_user = get_user_model().objects.create_user('other-family-member')
        other_member = Membership.objects.create(family=self.family, user=other_user, role='adult')
        self.create()
        response = self.public.get(self.feed)
        self.assertEqual(response.status_code, 200)
        components = Calendar.from_ical(response.content).walk('VEVENT')
        self.assertEqual(len(components), 1)
        self.assertNotIn('ATTENDEE', components[0])
        self.assertNotIn('ORGANIZER', components[0])
        member_feed = f"/calendar-feed/{self.grant['password']}/member/{other_member.pk}.ics"
        member_response = self.public.get(member_feed)
        self.assertEqual(member_response.status_code, 200)
        self.assertEqual(Calendar.from_ical(member_response.content).walk('VEVENT'), [])
