from datetime import datetime, timezone as utc
from unittest.mock import patch
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .integration_health import sync_with_health
from .models import Family, FamilyEvent, IntegrationSource, Membership
from .school_holidays import OFFICIAL_PAGE
PAGE='<a href="/fileadmin/holidays.ics">Download</a>'
def feed(end='20261017',uid='official-1',other=True):
    return (f'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:Herbstferien RLP Schuljahr 2026/2027\r\nDTSTART;VALUE=DATE:20261005\r\nDTEND;VALUE=DATE:{end}\r\nEND:VEVENT\r\n'+('BEGIN:VEVENT\r\nUID:christmas\r\nSUMMARY:Weihnachtsferien RLP Schuljahr 2026/2027\r\nDTSTART;VALUE=DATE:20261223\r\nDTEND;VALUE=DATE:20270109\r\nEND:VEVENT\r\n' if other else '')+'END:VCALENDAR\r\n').encode()
@patch('family.school_holidays.timezone.now',return_value=datetime(2026,10,9,tzinfo=utc.utc))
class SchoolHolidayTests(TestCase):
    def setUp(self):
        user=get_user_model().objects.create_user('holiday-owner')
        self.family=Family.objects.create(name='RLP',slug='holiday-rlp',timezone='America/New_York')
        Membership.objects.create(family=self.family,user=user,role='owner')
        self.client=APIClient();self.client.force_authenticate(user)
        self.source=IntegrationSource.objects.create(family=self.family,name='RLP Ferien',kind='school',config={'adapter':'rlp_school_holidays'})
        self.fetch=patch('family.school_holidays._get').start();self.addCleanup(patch.stopall);self.mock_feed(feed())
    def mock_feed(self,data):self.fetch.side_effect=[SimpleNamespace(text=PAGE),SimpleNamespace(content=data)]
    def test_dates_exclusive_end_geographic_timezone_and_daily_schedule(self,now):
        self.assertEqual(sync_with_health(self.source,force=True),2)
        autumn=FamilyEvent.objects.get(external_id='rlp-holiday:herbst:2026-2027')
        self.assertEqual(autumn.starts_at.isoformat(),'2026-10-04T22:00:00+00:00');self.assertEqual(autumn.ends_at.isoformat(),'2026-10-16T22:00:00+00:00')
        christmas=FamilyEvent.objects.get(external_id='rlp-holiday:weihnachts:2026-2027');self.assertEqual(christmas.starts_at.hour,23)
        self.assertEqual(christmas.payload['date_end_exclusive'],'2027-01-09');self.assertTrue(autumn.payload['all_day']);self.assertEqual(autumn.payload['source_url'],OFFICIAL_PAGE)
        self.source.refresh_from_db();self.assertEqual(self.source.last_sync_status,'success');self.assertIsNotNone(self.source.next_sync_at)
        self.fetch.reset_mock();self.assertEqual(sync_with_health(self.source),0);self.fetch.assert_not_called()
    def test_update_idempotent_with_changed_uid_and_removed_block(self,now):
        sync_with_health(self.source,force=True);event=FamilyEvent.objects.get(external_id='rlp-holiday:herbst:2026-2027')
        self.mock_feed(feed(end='20261018',uid='changed',other=False));sync_with_health(self.source,force=True)
        self.assertEqual(FamilyEvent.objects.filter(source=self.source).count(),1);event.refresh_from_db();self.assertEqual(event.payload['date_end_exclusive'],'2026-10-18')
        self.mock_feed(feed(end='20261018',uid='changed',other=False));sync_with_health(self.source,force=True);self.assertEqual(FamilyEvent.objects.get(source=self.source).pk,event.pk)
    def test_errors_preserve_dates_and_health(self,now):
        sync_with_health(self.source,force=True)
        for invalid in [feed(end='20261001'),b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n',b'not a calendar']:
            self.mock_feed(invalid)
            with self.assertRaises(ValueError):sync_with_health(self.source,force=True)
            self.assertEqual(FamilyEvent.objects.filter(source=self.source).count(),2);self.source.refresh_from_db();self.assertEqual(self.source.last_sync_status,'error');self.assertIsNotNone(self.source.last_success_at)
        self.fetch.side_effect=RuntimeError('network unavailable')
        with self.assertRaises(RuntimeError):sync_with_health(self.source,force=True)
        self.assertEqual(FamilyEvent.objects.filter(source=self.source).count(),2)
    def test_only_official_links(self,now):
        self.source.endpoint='https://evil.example/ics';sync_with_health(self.source,force=True);self.assertEqual(self.fetch.call_args_list[0].args[0],OFFICIAL_PAGE)
        self.fetch.side_effect=[SimpleNamespace(text='<a href="https://evil.example/holidays.ics">Download</a>')]
        with self.assertRaises(ValueError):sync_with_health(self.source,force=True)
        self.assertEqual(FamilyEvent.objects.filter(source=self.source).count(),2)
    def test_singleton_connect_and_permissions(self,now):
        body={'family':str(self.family.pk),'catalog_id':'rlp_school_holidays','values':{'adapter':'evil'}}
        response=self.client.post('/api/integration-hub/connect/',body,format='json');self.assertEqual(response.status_code,201);self.assertEqual(IntegrationSource.objects.count(),1);self.assertEqual(response.data['source']['config']['adapter'],'rlp_school_holidays')
        self.mock_feed(feed());self.assertEqual(self.client.post('/api/integration-hub/connect/',body,format='json').status_code,201);self.assertEqual(FamilyEvent.objects.count(),2)
        outsider=get_user_model().objects.create_user('holiday-outsider');self.client.force_authenticate(outsider)
        self.assertEqual(self.client.post('/api/integration-hub/connect/',body,format='json').status_code,403);self.assertIn(self.client.get('/api/events/').status_code,[200,403]);self.assertFalse(FamilyEvent.objects.filter(family__memberships__user=outsider).exists())
        Membership.objects.create(family=self.family,user=outsider,role='teen');self.assertEqual(self.client.post(f'/api/integration-hub/{self.source.pk}/sync/',{},format='json').status_code,403)
    def test_read_only_calendar_disconnect(self,now):
        sync_with_health(self.source,force=True);event=FamilyEvent.objects.filter(source=self.source).first()
        self.assertEqual(self.client.patch(f'/api/events/{event.pk}/',{'title':'fake'},format='json').status_code,403);self.assertEqual(self.client.delete(f'/api/events/{event.pk}/').status_code,403)
        own=FamilyEvent.objects.create(family=self.family,type='calendar.event',title='Own appointment')
        self.assertEqual(self.client.delete(f'/api/integrations/{self.source.pk}/').status_code,204);self.assertFalse(FamilyEvent.objects.filter(type='school.holiday').exists());self.assertTrue(FamilyEvent.objects.filter(pk=own.pk).exists())
