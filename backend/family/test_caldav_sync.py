from datetime import datetime, timedelta, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .caldav_models import CalDavConnection, CalDavEventBinding
from .caldav_secrets import decrypt_value, encrypt_credentials
from .caldav_sync import calendar_query_body, pull_remote, push_local, query_resources
from .models import Family, FamilyEvent, Membership


def remote_ics(uid="remote-1", title="Remote event"):
    return f'''BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:{uid}\r
DTSTART:20261020T080000Z\r
DTEND:20261020T090000Z\r
SUMMARY:{title}\r
LOCATION:Kitchen\r
END:VEVENT\r
END:VCALENDAR\r
'''.encode()


@override_settings(SECRET_KEY="caldav-sync-tests")
class CalDavSyncTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("sync-owner")
        self.family = Family.objects.create(name="Sync Family", slug="sync-family", timezone="Europe/Berlin")
        self.member = Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER, display_name="Alex")
        self.connection = CalDavConnection.objects.create(
            scope=CalDavConnection.Scope.FAMILY,
            name="Apple · Alex",
            family=self.family,
            member=self.member,
            created_by=self.user,
            access_mode=CalDavConnection.AccessMode.READ_WRITE,
            calendar_href="https://calendar.example.test/calendars/alex/",
            credentials_encrypted=encrypt_credentials(
                server_url="https://calendar.example.test/dav",
                username="alex@example.test",
                password="app-password",
            ),
        )
        self.start = datetime(2026, 10, 1, tzinfo=utc.utc)
        self.end = datetime(2026, 11, 1, tzinfo=utc.utc)

    def test_calendar_query_uses_server_side_time_range(self):
        body = calendar_query_body(self.start, self.end).decode()
        self.assertIn('<c:time-range start="20261001T000000Z" end="20261101T000000Z"/>', body)
        calls = []

        def requester(url, **kwargs):
            calls.append((url, kwargs))
            payload = b'''<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response><d:href>/calendars/alex/a.ics</d:href><d:propstat><d:prop><d:getetag>"e1"</d:getetag><c:calendar-data>BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR</c:calendar-data></d:prop></d:propstat></d:response></d:multistatus>'''
            return url, 207, {}, payload

        rows = query_resources(self.connection, self.start, self.end, requester=requester)
        self.assertEqual(len(rows), 1)
        self.assertEqual(calls[0][1]["method"], "REPORT")
        self.assertEqual(calls[0][1]["headers"]["Depth"], "1")
        self.assertIn(b"time-range", calls[0][1]["body"])

    @patch("family.caldav_sync.query_resources")
    def test_pull_projects_remote_event_without_exposing_remote_identity(self, query):
        query.return_value = [{
            "href": "https://calendar.example.test/calendars/alex/private-token.ics",
            "etag": '"remote-v1"',
            "data": remote_ics(),
        }]
        result = pull_remote(self.connection, self.start, self.end)
        self.assertEqual(result["pulled"], 1)
        event = FamilyEvent.objects.get(source__config__caldav_connection=str(self.connection.id))
        self.assertEqual(event.title, "Remote event")
        self.assertEqual(list(event.participants.values_list("id", flat=True)), [self.member.id])
        self.assertNotIn("private-token", str(event.payload))
        self.assertNotIn("remote-1", str(event.payload))
        binding = CalDavEventBinding.objects.get(connection=self.connection, event=event)
        self.assertEqual(binding.remote_uid, "remote-1")
        self.assertEqual(decrypt_value(binding.remote_href_encrypted), "https://calendar.example.test/calendars/alex/private-token.ics")
        self.assertNotIn("private-token", binding.remote_href_encrypted)

    @patch("family.caldav_sync.safe_request")
    def test_read_write_put_uses_if_none_match_then_if_match(self, request):
        request.return_value = ("https://calendar.example.test/calendars/alex/event.ics", 201, {"ETag": '"v1"'}, b"")
        event = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Dentist",
            starts_at=datetime(2026, 10, 20, 8, tzinfo=utc.utc),
            ends_at=datetime(2026, 10, 20, 9, tzinfo=utc.utc),
            is_family_event=False,
        )
        event.participants.add(self.member)
        first = push_local(self.connection, self.start, self.end)
        self.assertEqual(first["pushed"], 1)
        self.assertEqual(request.call_args.kwargs["headers"]["If-None-Match"], "*")
        binding = CalDavEventBinding.objects.get(connection=self.connection, event=event)
        self.assertEqual(binding.etag, '"v1"')

        event.title = "Dentist moved"
        event.save(update_fields=["title", "updated_at"])
        request.reset_mock()
        request.return_value = ("https://calendar.example.test/calendars/alex/event.ics", 204, {"ETag": '"v2"'}, b"")
        second = push_local(self.connection, self.start, self.end)
        self.assertEqual(second["pushed"], 1)
        self.assertEqual(request.call_args.kwargs["headers"]["If-Match"], '"v1"')
        binding.refresh_from_db()
        self.assertEqual(binding.etag, '"v2"')

    @patch("family.caldav_sync.safe_request")
    def test_etag_conflict_does_not_overwrite_remote(self, request):
        event = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Conflict",
            starts_at=datetime(2026, 10, 20, 8, tzinfo=utc.utc),
            ends_at=datetime(2026, 10, 20, 9, tzinfo=utc.utc),
            is_family_event=True,
        )
        binding = CalDavEventBinding.objects.create(
            connection=self.connection,
            event=event,
            remote_uid=f"familyos-{event.pk}@familyos",
            remote_href_encrypted=__import__("family.caldav_secrets", fromlist=["encrypt_value"]).encrypt_value("https://calendar.example.test/calendars/alex/event.ics"),
            etag='"old"',
            local_version=max(0, event.version - 1),
        )
        request.return_value = ("https://calendar.example.test/calendars/alex/event.ics", 412, {}, b"")
        result = push_local(self.connection, self.start, self.end)
        self.assertEqual(result["conflicts"], 1)
        binding.refresh_from_db()
        self.assertEqual(binding.etag, '"old"')

    @patch("family.caldav_sync.safe_request")
    def test_read_only_mode_never_writes(self, request):
        self.connection.access_mode = CalDavConnection.AccessMode.READ
        self.connection.save(update_fields=["access_mode", "updated_at"])
        FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title="Local",
            starts_at=datetime(2026, 10, 20, 8, tzinfo=utc.utc),
            is_family_event=True,
        )
        self.assertEqual(push_local(self.connection, self.start, self.end)["pushed"], 0)
        request.assert_not_called()


@override_settings(SECRET_KEY="caldav-api-tests")
class CalDavSelectionApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("api-owner")
        self.family = Family.objects.create(name="API Family", slug="api-family")
        self.member = Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.client = APIClient(); self.client.force_authenticate(self.user)
        response = self.client.post("/api/caldav-connections/", {
            "scope": "family",
            "family": str(self.family.id),
            "member": str(self.member.id),
            "name": "Apple",
            "access_mode": "read_write",
            "server_url": "https://calendar.example.test/dav",
            "username": "alice",
            "password": "secret",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.connection_id = response.data["id"]

    @patch("family.caldav_views.discover_calendars")
    def test_discovery_returns_opaque_key_and_selection_stays_server_side(self, discover):
        discover.return_value = [{
            "href": "https://calendar.example.test/calendars/alice/private/",
            "display_name": "Privat",
            "components": ["VEVENT"],
            "sync_token_supported": True,
        }]
        response = self.client.post(f"/api/caldav-connections/{self.connection_id}/discover/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        calendar = response.data["calendars"][0]
        self.assertIn("calendar_key", calendar)
        self.assertNotIn("href", calendar)
        self.assertNotIn("calendar.example.test", str(response.data))

        selected = self.client.post(
            f"/api/caldav-connections/{self.connection_id}/select-calendar/",
            {"calendar_key": calendar["calendar_key"]},
            format="json",
        )
        self.assertEqual(selected.status_code, 200, selected.data)
        row = CalDavConnection.objects.get(id=self.connection_id)
        self.assertEqual(row.calendar_href, "https://calendar.example.test/calendars/alice/private/")
        detail = self.client.get(f"/api/caldav-connections/{self.connection_id}/")
        self.assertTrue(detail.data["calendar_selected"])
        self.assertNotIn("calendar_href", detail.data)
