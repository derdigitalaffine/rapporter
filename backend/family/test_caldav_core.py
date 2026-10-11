import socket
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .caldav_discovery import CalDavDiscoveryError, _parse_xml, discover_calendars, safe_propfind, validate_endpoint
from .caldav_models import CalDavConnection
from .caldav_secrets import decrypt_credentials
from .models import Family, Membership


def resolver_for(mapping):
    def resolve(host, port, type=None):
        addresses = mapping.get(host, [])
        return [
            (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))
            for address in addresses
        ]
    return resolve


class CalDavConnectionApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("caldav-owner")
        self.adult = User.objects.create_user("caldav-adult")
        self.teen = User.objects.create_user("caldav-teen")
        self.other = User.objects.create_user("caldav-other")
        self.family = Family.objects.create(name="CalDAV Family", slug="caldav-family")
        self.other_family = Family.objects.create(name="Other", slug="caldav-other")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family, user=self.adult, role=Membership.Role.ADULT)
        Membership.objects.create(family=self.family, user=self.teen, role=Membership.Role.TEEN)
        Membership.objects.create(family=self.other_family, user=self.other, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def _create(self, **changes):
        payload = {
            "scope": "personal",
            "name": "Mein Nextcloud",
            "server_url": "https://calendar.example.test/dav?opaque=secret",
            "username": "alice@example.test",
            "password": "app-password-secret",
            **changes,
        }
        return self.client.post("/api/caldav-connections/", payload, format="json")

    def test_personal_credentials_are_encrypted_and_never_serialized(self):
        response = self._create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["credential_state"], "configured")
        self.assertNotIn("server_url", response.data)
        self.assertNotIn("username", response.data)
        self.assertNotIn("password", response.data)

        row = CalDavConnection.objects.get(id=response.data["id"])
        self.assertEqual(row.owner, self.owner)
        self.assertIsNone(row.family)
        self.assertNotIn("app-password-secret", row.credentials_encrypted)
        self.assertNotIn("calendar.example.test", row.credentials_encrypted)
        self.assertEqual(
            decrypt_credentials(row.credentials_encrypted),
            {
                "server_url": "https://calendar.example.test/dav?opaque=secret",
                "username": "alice@example.test",
                "password": "app-password-secret",
            },
        )

        detail = self.client.get(f"/api/caldav-connections/{row.id}/")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["id"], str(row.id))

        self.client.force_authenticate(self.other)
        listed = self.client.get("/api/caldav-connections/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["results"], [])

    def test_family_connection_is_managed_only_by_owner_or_adult(self):
        response = self._create(scope="family", family=str(self.family.id), name="Familienkalender")
        self.assertEqual(response.status_code, 201, response.data)
        connection_id = response.data["id"]

        self.client.force_authenticate(self.adult)
        self.assertEqual(self.client.get(f"/api/caldav-connections/{connection_id}/").status_code, 200)

        self.client.force_authenticate(self.teen)
        self.assertEqual(self.client.get(f"/api/caldav-connections/{connection_id}/").status_code, 404)
        denied = self._create(scope="family", family=str(self.family.id), name="Nicht erlaubt")
        self.assertEqual(denied.status_code, 403)

    def test_scope_and_family_cannot_be_swapped_by_patch(self):
        response = self._create()
        connection_id = response.data["id"]
        changed = self.client.patch(
            f"/api/caldav-connections/{connection_id}/",
            {"scope": "family", "family": str(self.family.id)},
            format="json",
        )
        self.assertEqual(changed.status_code, 400)
        row = CalDavConnection.objects.get(id=connection_id)
        self.assertEqual(row.scope, CalDavConnection.Scope.PERSONAL)
        self.assertIsNone(row.family)

    @patch("family.caldav_views.discover_calendars")
    def test_discovery_returns_sanitized_metadata_only(self, mocked_discover):
        mocked_discover.return_value = [{
            "href": "https://calendar.example.test/private/calendar/",
            "display_name": "Privat",
            "components": ["VEVENT"],
            "sync_token_supported": True,
        }]
        response = self._create()
        connection_id = response.data["id"]
        discovered = self.client.post(f"/api/caldav-connections/{connection_id}/discover/", {}, format="json")
        self.assertEqual(discovered.status_code, 200, discovered.data)
        self.assertEqual(discovered.data["calendar_count"], 1)
        self.assertEqual(discovered.data["calendars"][0]["display_name"], "Privat")
        self.assertNotIn("href", discovered.data["calendars"][0])
        self.assertNotIn("calendar.example.test", str(discovered.data))
        self.assertNotIn("app-password-secret", str(discovered.data))
        row = CalDavConnection.objects.get(id=connection_id)
        self.assertIsNotNone(row.last_discovered_at)
        self.assertEqual(row.last_error_code, "")

    @patch("family.caldav_views.discover_calendars", side_effect=CalDavDiscoveryError("caldav_address_rejected"))
    def test_discovery_exposes_stable_error_code_without_secret(self, mocked_discover):
        response = self._create()
        connection_id = response.data["id"]
        failed = self.client.post(f"/api/caldav-connections/{connection_id}/discover/", {}, format="json")
        self.assertEqual(failed.status_code, 400)
        self.assertEqual(failed.data["detail"], "caldav_address_rejected")
        self.assertNotIn("app-password-secret", str(failed.data))
        self.assertEqual(CalDavConnection.objects.get(id=connection_id).last_error_code, "caldav_address_rejected")


class CalDavSsrfTests(TestCase):
    public = staticmethod(resolver_for({"calendar.example.test": ["93.184.216.34"]}))
    private = staticmethod(resolver_for({"calendar.example.test": ["10.0.0.25"]}))

    def test_https_public_address_is_allowed_and_pinned(self):
        endpoint = validate_endpoint("https://calendar.example.test/dav", resolver=self.public)
        self.assertEqual(endpoint.host, "calendar.example.test")
        self.assertEqual(endpoint.port, 443)
        self.assertEqual(endpoint.ip, "93.184.216.34")

    def test_private_loopback_link_local_and_mixed_dns_are_blocked_by_default(self):
        for address in ("10.0.0.25", "127.0.0.1", "169.254.169.254", "::1", "fe80::1"):
            with self.subTest(address=address):
                with self.assertRaisesMessage(CalDavDiscoveryError, "caldav_address_rejected"):
                    validate_endpoint(
                        "https://calendar.example.test/dav",
                        resolver=resolver_for({"calendar.example.test": [address]}),
                    )
        with self.assertRaisesMessage(CalDavDiscoveryError, "caldav_address_rejected"):
            validate_endpoint(
                "https://calendar.example.test/dav",
                resolver=resolver_for({"calendar.example.test": ["93.184.216.34", "10.0.0.25"]}),
            )

    @override_settings(CALDAV_ALLOW_PRIVATE_NETWORKS=True)
    def test_operator_can_enable_private_lan_but_not_loopback(self):
        endpoint = validate_endpoint("https://calendar.example.test/dav", resolver=self.private)
        self.assertEqual(endpoint.ip, "10.0.0.25")
        with self.assertRaisesMessage(CalDavDiscoveryError, "caldav_address_rejected"):
            validate_endpoint(
                "https://calendar.example.test/dav",
                resolver=resolver_for({"calendar.example.test": ["127.0.0.1"]}),
            )

    def test_http_userinfo_fragment_and_unapproved_ports_fail_closed(self):
        cases = [
            ("http://calendar.example.test/dav", "caldav_url_scheme_rejected"),
            ("https://alice:secret@calendar.example.test/dav", "caldav_url_userinfo_rejected"),
            ("https://calendar.example.test/dav#private", "caldav_url_fragment_rejected"),
            ("https://calendar.example.test:8443/dav", "caldav_port_rejected"),
        ]
        for url, code in cases:
            with self.subTest(url=url):
                with self.assertRaisesMessage(CalDavDiscoveryError, code):
                    validate_endpoint(url, resolver=self.public)

    @override_settings(CALDAV_ALLOW_HTTP=True, CALDAV_ALLOWED_PORTS=(80,))
    def test_http_requires_explicit_operator_opt_in(self):
        endpoint = validate_endpoint("http://calendar.example.test/dav", resolver=self.public)
        self.assertEqual(endpoint.port, 80)

    @patch("family.caldav_discovery._request_once")
    def test_redirect_target_is_dns_validated_again(self, request_once):
        request_once.return_value = (302, {"Location": "https://internal.example.test/dav"}, b"")
        resolver = resolver_for({
            "calendar.example.test": ["93.184.216.34"],
            "internal.example.test": ["10.0.0.25"],
        })
        with self.assertRaisesMessage(CalDavDiscoveryError, "caldav_address_rejected"):
            safe_propfind(
                "https://calendar.example.test/dav",
                username="alice",
                password="secret",
                resolver=resolver,
            )
        self.assertEqual(request_once.call_count, 1)

    def test_xml_entities_and_doctype_are_rejected_before_parse(self):
        with self.assertRaisesMessage(CalDavDiscoveryError, "caldav_xml_unsafe"):
            _parse_xml(b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>')


class CalDavDiscoveryParserTests(TestCase):
    def test_principal_home_and_calendar_collection_are_discovered(self):
        responses = iter([
            ("https://calendar.example.test/dav", b'''<d:multistatus xmlns:d="DAV:"><d:response><d:propstat><d:prop><d:current-user-principal><d:href>/principals/alice/</d:href></d:current-user-principal></d:prop></d:propstat></d:response></d:multistatus>'''),
            ("https://calendar.example.test/principals/alice/", b'''<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response><d:propstat><d:prop><c:calendar-home-set><d:href>/calendars/alice/</d:href></c:calendar-home-set></d:prop></d:propstat></d:response></d:multistatus>'''),
            ("https://calendar.example.test/calendars/alice/", b'''<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response><d:href>/calendars/alice/private/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/><c:calendar/></d:resourcetype><d:displayname>Privat</d:displayname><c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set><d:sync-token>token-1</d:sync-token></d:prop></d:propstat></d:response></d:multistatus>'''),
        ])
        calls = []

        def fake_propfind(url, **kwargs):
            calls.append((url, kwargs["depth"]))
            return next(responses)

        calendars = discover_calendars(
            server_url="https://calendar.example.test/dav",
            username="alice",
            password="secret",
            propfind=fake_propfind,
        )
        self.assertEqual(calls, [
            ("https://calendar.example.test/dav", "0"),
            ("https://calendar.example.test/principals/alice/", "0"),
            ("https://calendar.example.test/calendars/alice/", "1"),
        ])
        self.assertEqual(calendars, [{
            "href": "https://calendar.example.test/calendars/alice/private/",
            "display_name": "Privat",
            "components": ["VEVENT"],
            "sync_token_supported": True,
        }])
