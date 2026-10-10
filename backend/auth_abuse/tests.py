from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections, connection
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings

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
