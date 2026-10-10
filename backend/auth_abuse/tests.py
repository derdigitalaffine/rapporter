import socket
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings

from config.settings import _TrustedProxyCidrs

from .models import AuthAbuseBucket
from .service import POLICIES, client_ip, enforce, network_identity


STABLE_SCOPES = {
    "login.password",
    "login.passkey.options",
    "login.passkey.verify",
    "reauth.password",
    "password_reset.request",
    "email_verification.resend",
    "invite.create",
    "invite.resend",
    "webauthn.registration.options",
    "webauthn.authentication.options",
    "superadmin.sensitive_action",
}


@override_settings(AUTH_ABUSE_HMAC_KEY="test-only-abuse-key")
class AuthAbuseServiceTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_stable_scope_contract_is_complete(self):
        self.assertTrue(STABLE_SCOPES.issubset(POLICIES))

    @override_settings(AUTH_TRUSTED_PROXY_CIDRS=[])
    def test_untrusted_forwarded_for_is_ignored(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_FORWARDED_FOR="198.51.100.25",
        )
        self.assertEqual(str(client_ip(request)), "203.0.113.10")

    @override_settings(AUTH_TRUSTED_PROXY_CIDRS=["203.0.113.0/24"])
    def test_forwarded_for_is_used_only_from_trusted_proxy(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_FORWARDED_FOR="198.51.100.25, 203.0.113.11",
        )
        self.assertEqual(str(client_ip(request)), "198.51.100.25")

    @override_settings(AUTH_TRUSTED_PROXY_CIDRS=_TrustedProxyCidrs([], ["caddy"]))
    @patch("config.settings.socket.getaddrinfo")
    def test_trusted_proxy_hostname_tracks_exact_compose_peer(self, getaddrinfo):
        getaddrinfo.side_effect = [
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.20.0.3", 0))],
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.20.0.4", 0))],
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.20.0.4", 0))],
        ]
        first = self.factory.get(
            "/",
            REMOTE_ADDR="172.20.0.3",
            HTTP_X_FORWARDED_FOR="198.51.100.25",
        )
        after_proxy_restart = self.factory.get(
            "/",
            REMOTE_ADDR="172.20.0.4",
            HTTP_X_FORWARDED_FOR="198.51.100.26",
        )
        spoofed_from_other_peer = self.factory.get(
            "/",
            REMOTE_ADDR="172.20.0.5",
            HTTP_X_FORWARDED_FOR="198.51.100.27",
        )
        self.assertEqual(str(client_ip(first)), "198.51.100.25")
        self.assertEqual(str(client_ip(after_proxy_restart)), "198.51.100.26")
        self.assertEqual(str(client_ip(spoofed_from_other_peer)), "172.20.0.5")

    @override_settings(AUTH_TRUSTED_PROXY_CIDRS=_TrustedProxyCidrs([], ["missing-proxy"]))
    @patch("config.settings.socket.getaddrinfo", side_effect=socket.gaierror("not found"))
    def test_unresolvable_trusted_proxy_hostname_fails_closed(self, _getaddrinfo):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="172.20.0.3",
            HTTP_X_FORWARDED_FOR="198.51.100.25",
        )
        self.assertEqual(str(client_ip(request)), "172.20.0.3")

    @override_settings(AUTH_TRUSTED_PROXY_CIDRS=[], AUTH_ABUSE_IPV6_PREFIX=64)
    def test_ipv6_network_identity_uses_prefix(self):
        request = self.factory.get("/", REMOTE_ADDR="2001:db8:abcd:1234:1111:2222:3333:4444")
        self.assertEqual(network_identity(request), "2001:db8:abcd:1234::/64")

    def test_persistent_keys_do_not_store_raw_identifier_or_ip(self):
        request = self.factory.post("/", REMOTE_ADDR="198.51.100.42")
        decision = enforce("login.password", request=request, identifier="Alice@Example.com")
        self.assertTrue(decision.allowed)
        buckets = list(AuthAbuseBucket.objects.filter(scope="login.password"))
        self.assertGreaterEqual(len(buckets), 6)
        for bucket in buckets:
            self.assertEqual(len(bucket.key_hash), 64)
            self.assertNotIn("alice", bucket.key_hash.lower())
            self.assertNotIn("198.51.100.42", bucket.key_hash)

    def test_burst_limit_blocks_after_configured_identifier_attempts(self):
        request = self.factory.post("/", REMOTE_ADDR="198.51.100.43")
        decisions = [
            enforce("login.password", request=request, identifier="victim@example.com")
            for _ in range(POLICIES["login.password"].burst.limit + 1)
        ]
        self.assertTrue(all(decision.allowed for decision in decisions[:-1]))
        self.assertFalse(decisions[-1].allowed)
        self.assertGreater(decisions[-1].retry_after, 0)


@override_settings(AUTH_ABUSE_HMAC_KEY="parallel-test-only-abuse-key")
class AuthAbuseConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Row-lock concurrency test requires PostgreSQL")

    @staticmethod
    def _attempt():
        close_old_connections()
        try:
            request = RequestFactory().post("/", REMOTE_ADDR="198.51.100.44")
            return enforce("password_reset.request", request=request, identifier="parallel@example.com").allowed
        finally:
            close_old_connections()

    def test_parallel_workers_share_one_locked_budget(self):
        limit = POLICIES["password_reset.request"].burst.limit
        with ThreadPoolExecutor(max_workers=limit + 4) as executor:
            results = list(executor.map(lambda _: self._attempt(), range(limit + 4)))
        self.assertLessEqual(sum(results), limit)
        self.assertGreaterEqual(len(results) - sum(results), 1)
