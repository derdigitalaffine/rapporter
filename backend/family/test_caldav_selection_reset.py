from datetime import datetime, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .caldav_models import CalDavConnection, CalDavEventBinding
from .caldav_secrets import encrypt_value
from .caldav_views import calendar_key
from .models import Family, FamilyEvent, IntegrationSource, Membership


@override_settings(SECRET_KEY='caldav-reset-tests')
class CalDavSelectionResetTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('reset-owner')
        self.other_user = User.objects.create_user('reset-other')
        self.family = Family.objects.create(name='Reset Family', slug='reset-family')
        self.member = Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.other_member = Membership.objects.create(family=self.family, user=self.other_user, role=Membership.Role.ADULT)
        self.client = APIClient(); self.client.force_authenticate(self.user)
        created = self.client.post('/api/caldav-connections/', {
            'scope': 'family',
            'family': str(self.family.id),
            'member': str(self.member.id),
            'name': 'Apple',
            'access_mode': 'read_write',
            'server_url': 'https://calendar.example.test/dav',
            'username': 'alice',
            'password': 'secret',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.connection = CalDavConnection.objects.get(pk=created.data['id'])
        self.first_href = 'https://calendar.example.test/calendars/alice/first/'
        self.second_href = 'https://calendar.example.test/calendars/alice/second/'
        self.connection.calendar_href = self.first_href
        self.connection.save(update_fields=['calendar_href_encrypted', 'updated_at'])

    def projected_row(self):
        source = IntegrationSource.objects.create(
            family=self.family,
            name='Apple',
            kind=IntegrationSource.Kind.ICS,
            config={'adapter': 'caldav', 'caldav_connection': str(self.connection.id)},
        )
        event = FamilyEvent.objects.create(
            family=self.family,
            source=source,
            type='calendar.event',
            title='Old remote event',
            starts_at=datetime(2026, 10, 20, 8, tzinfo=utc.utc),
            external_id='caldav:old',
        )
        binding = CalDavEventBinding.objects.create(
            connection=self.connection,
            event=event,
            remote_uid='old-1',
            remote_href_encrypted=encrypt_value(self.first_href + 'old.ics'),
            etag='"old"',
            local_version=event.version,
        )
        return source, event, binding

    @patch('family.caldav_views.discover_calendars')
    def test_selecting_different_collection_clears_old_projection_and_registers_new_source(self, discover):
        source, event, binding = self.projected_row()
        discover.return_value = [{
            'href': self.second_href,
            'display_name': 'Second',
            'components': ['VEVENT'],
            'sync_token_supported': True,
        }]
        selected = self.client.post(
            f'/api/caldav-connections/{self.connection.id}/select-calendar/',
            {'calendar_key': calendar_key(self.connection, self.second_href)},
            format='json',
        )
        self.assertEqual(selected.status_code, 200, selected.data)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.calendar_href, self.second_href)
        self.assertFalse(IntegrationSource.objects.filter(pk=source.pk).exists())
        self.assertFalse(FamilyEvent.objects.filter(pk=event.pk).exists())
        self.assertFalse(CalDavEventBinding.objects.filter(pk=binding.pk).exists())
        replacement = IntegrationSource.objects.get(config__caldav_connection=str(self.connection.id))
        self.assertEqual(replacement.name, self.connection.name)
        self.assertEqual(replacement.config['adapter'], 'caldav')

    @patch('family.caldav_views.discover_calendars')
    def test_first_collection_selection_registers_health_source_without_manual_sync(self, discover):
        self.connection.calendar_href_encrypted = ''
        self.connection.save(update_fields=['calendar_href_encrypted', 'updated_at'])
        discover.return_value = [{
            'href': self.first_href,
            'display_name': 'First',
            'components': ['VEVENT'],
            'sync_token_supported': True,
        }]
        response = self.client.post(
            f'/api/caldav-connections/{self.connection.id}/select-calendar/',
            {'calendar_key': calendar_key(self.connection, self.first_href)},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(IntegrationSource.objects.filter(
            family=self.family,
            config__caldav_connection=str(self.connection.id),
            config__adapter='caldav',
        ).exists())

    def test_credential_change_requires_new_calendar_selection_and_clears_projection(self):
        source, event, binding = self.projected_row()
        changed = self.client.patch(f'/api/caldav-connections/{self.connection.id}/', {
            'server_url': 'https://calendar.example.test/new-dav',
            'username': 'alice',
            'password': 'new-secret',
        }, format='json')
        self.assertEqual(changed.status_code, 200, changed.data)
        self.connection.refresh_from_db()
        self.assertFalse(self.connection.calendar_href_encrypted)
        self.assertFalse(IntegrationSource.objects.filter(pk=source.pk).exists())
        self.assertFalse(FamilyEvent.objects.filter(pk=event.pk).exists())
        self.assertFalse(CalDavEventBinding.objects.filter(pk=binding.pk).exists())

    def test_member_mapping_is_immutable_after_connection_creation(self):
        rejected = self.client.patch(
            f'/api/caldav-connections/{self.connection.id}/',
            {'member': str(self.other_member.id)},
            format='json',
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn('member', rejected.data)
