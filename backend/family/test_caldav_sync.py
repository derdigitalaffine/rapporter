from datetime import datetime, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .caldav_models import CalDavConnection, CalDavEventBinding
from .caldav_secrets import decrypt_value, encrypt_credentials, encrypt_value
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
            calendar_href_encrypted=encrypt_value("https://calendar.example.test/calendars/alex/"),
            credentials_encrypted=encrypt_credentials(
                server_url="https://calendar.example.test/dav",
                username="alex@example.test",
                password="app-password",
            ),
        )
        self.start = datetime(2026, 10, 1, tzinfo=utc.utc)
        self.end = datetime(2026, 11, 1, tzinfo=utc.utc)

    def native_event(self, title="Local", family_event=True):
        event = FamilyEvent.objects.create(
            family=self.family,
            type="calendar.event",
            title=title,
            starts_at=datetime(2026, 10, 20, 8, tzinfo=utc.utc),
            ends_at=datetime(2026, 10, 20, 9, tzinfo=utc.utc),
            is_family_event=family_event,
        )
        if not family_event:
            event.participants.add(self.member)
        return event

    def binding_for(self, event, *, uid=None, etag='"v1"'):
        return CalDavEventBinding.objects.create(
            connection=self.connection,
            event=event,
            remote_uid=uid or f"familyos-{event.pk}@familyos",
            remote_href_encrypted=encrypt_value(f"https://calendar.example.test/calendars/alex/{event.pk}.ics"),
            etag=etag,
            local_version=event.version,
        )

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
        event = self.native_event("Dentist", family_event=False)
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
        event = self.native_event("Conflict")
        binding = self.binding_for(event, etag='"old"')
        event.title = "Local changed"
        event.save(update_fields=["title", "updated_at"])
        request.return_value = (decrypt_value(binding.remote_href_encrypted), 412, {}, b"")
        result = push_local(self.connection, self.start, self.end)
        self.assertEqual(result["conflicts"], 1)
        binding.refresh_from_db()
        self.assertEqual(binding.etag, '"old"')

    @patch("family.caldav_sync.query_resources")
    def test_pull_detects_simultaneous_local_and_remote_edit_without_last_write_wins(self, query):
        event = self.native_event("Original")
        binding = self.binding_for(event, uid="shared-1", etag='"remote-v1"')
        event.title = "Local edit"
        event.save(update_fields=["title", "updated_at"])
        local_version = event.version
        query.return_value = [{
            "href": decrypt_value(binding.remote_href_encrypted),
            "etag": '"remote-v2"',
            "data": remote_ics(uid="shared-1", title="Remote edit"),
        }]
        result = pull_remote(self.connection, self.start, self.end)
        event.refresh_from_db(); binding.refresh_from_db()
        self.assertEqual(result["conflicts"], 1)
        self.assertEqual(event.title, "Local edit")
        self.assertEqual(event.version, local_version)
        self.assertEqual(binding.etag, '"remote-v1"')
        self.assertNotEqual(binding.local_version, event.version)

    @patch("family.caldav_sync.query_resources")
    @patch("family.caldav_sync.safe_request")
    def test_local_delete_stays_tombstoned_until_conditional_remote_delete(self, request, query):
        event = self.native_event("Delete me")
        binding = self.binding_for(event, uid="delete-1", etag='"remote-v1"')
        href = decrypt_value(binding.remote_href_encrypted)
        event.delete()
        binding.refresh_from_db()
        self.assertIsNone(binding.event_id)
        query.return_value = [{"href": href, "etag": '"remote-v1"', "data": remote_ics(uid="delete-1", title="Delete me")}]
        pull_remote(self.connection, self.start, self.end)
        binding.refresh_from_db()
        self.assertIsNone(binding.event_id)
        self.assertFalse(FamilyEvent.objects.filter(title="Delete me").exists())

        request.return_value = (href, 204, {}, b"")
        result = push_local(self.connection, self.start, self.end)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(request.call_args.kwargs["method"], "DELETE")
        self.assertEqual(request.call_args.kwargs["headers"]["If-Match"], '"remote-v1"')
        self.assertFalse(CalDavEventBinding.objects.filter(pk=binding.pk).exists())

    @patch("family.caldav_sync.query_resources")
    @patch("family.caldav_sync.safe_request")
    def test_remote_edit_after_local_delete_becomes_conflict_not_destructive_delete(self, request, query):
        event = self.native_event("Delete conflict")
        binding = self.binding_for(event, uid="delete-conflict", etag='"remote-v1"')
        href = decrypt_value(binding.remote_href_encrypted)
        event.delete()
        query.return_value = [{"href": href, "etag": '"remote-v2"', "data": remote_ics(uid="delete-conflict", title="Remote changed")}]
        pull_remote(self.connection, self.start, self.end)
        binding.refresh_from_db()
        self.assertEqual(binding.etag, '"remote-v1"')
        request.return_value = (href, 412, {}, b"")
        result = push_local(self.connection, self.start, self.end)
        self.assertEqual(result["conflicts"], 1)
        self.assertTrue(CalDavEventBinding.objects.filter(pk=binding.pk).exists())

    @patch("family.caldav_sync.safe_request")
    def test_read_only_mode_never_writes(self, request):
        self.connection.access_mode = CalDavConnection.AccessMode.READ
        self.connection.save(update_fields=["access_mode", "updated_at"])
        self.native_event()
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

    def test_second_connection_for_same_member_is_rejected_cleanly(self):
        duplicate = self.client.post("/api/caldav-connections/", {
            "scope": "family",
            "family": str(self.family.id),
            "member": str(self.member.id),
            "name": "Second",
            "access_mode": "read",
            "server_url": "https://other.example.test/dav",
            "username": "alice",
            "password": "secret",
        }, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("member", duplicate.data)

    @patch("family.caldav_views.discover_calendars")
    def test_discovery_returns_opaque_key_and_selection_stays_server_side(self, discover):
        private_href = "https://calendar.example.test/calendars/alice/private-token/"
        discover.return_value = [{
            "href": private_href,
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
        self.assertEqual(row.calendar_href, private_href)
        self.assertNotIn("private-token", row.calendar_href_encrypted)
        self.assertNotIn("calendar.example.test", row.calendar_href_encrypted)
        detail = self.client.get(f"/api/caldav-connections/{self.connection_id}/")
        self.assertTrue(detail.data["calendar_selected"])
        self.assertNotIn("calendar_href", detail.data)
        self.assertNotIn("calendar_href_encrypted", detail.data)
