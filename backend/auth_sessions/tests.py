from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .cookies import ACCESS_COOKIE, REFRESH_COOKIE
from .models import AuthSession
from .service import create_session, revoke_all_user_sessions, rotate_refresh


@override_settings(AUTH_ABUSE_HMAC_KEY="session-tests-abuse-key")
class AuthSessionApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="session-user",
            email="session@example.com",
            password="session-pass-123",
        )

    def login(self, *, client=None, remote="198.51.100.70", user_agent="Mozilla/5.0 (Macintosh) Chrome/123 Safari/537.36"):
        client = client or APIClient()
        response = client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "session-pass-123"},
            format="json",
            REMOTE_ADDR=remote,
            HTTP_USER_AGENT=user_agent,
        )
        self.assertEqual(response.status_code, 200, response.data)
        return client, response

    def test_login_creates_exactly_one_session_and_sid_claims(self):
        client, response = self.login()
        self.assertEqual(AuthSession.objects.filter(user=self.user).count(), 1)
        session = AuthSession.objects.get(user=self.user)
        self.assertEqual(response.data["session"]["id"], str(session.pk))
        self.assertIn("Chrome", session.client_label)
        access = AccessToken(client.cookies[ACCESS_COOKIE].value)
        refresh = RefreshToken(client.cookies[REFRESH_COOKIE].value)
        self.assertEqual(access["sid"], str(session.pk))
        self.assertEqual(refresh["sid"], str(session.pk))
        self.assertEqual(access["auth_method"], "password")
        self.assertIn("auth_time", access)

    def test_refresh_rotates_jti_but_preserves_logical_sid(self):
        client, _ = self.login()
        before = RefreshToken(client.cookies[REFRESH_COOKIE].value)
        response = client.post("/api/auth/refresh/", format="json")
        self.assertEqual(response.status_code, 200, response.data)
        after = RefreshToken(client.cookies[REFRESH_COOKIE].value)
        self.assertEqual(before["sid"], after["sid"])
        self.assertNotEqual(before["jti"], after["jti"])
        session = AuthSession.objects.get(pk=after["sid"])
        self.assertEqual(session.current_refresh_jti, after["jti"])
        self.assertEqual(session.previous_refresh_jti, before["jti"])

    def test_logout_revokes_server_side_and_clears_cookies(self):
        client, _ = self.login()
        sid = RefreshToken(client.cookies[REFRESH_COOKIE].value)["sid"]
        response = client.post("/api/auth/logout/", format="json")
        self.assertEqual(response.status_code, 200)
        session = AuthSession.objects.get(pk=sid)
        self.assertIsNotNone(session.revoked_at)
        self.assertEqual(session.revoked_reason, "logout")
        self.assertEqual(client.cookies[ACCESS_COOKIE].value, "")
        self.assertEqual(client.cookies[REFRESH_COOKIE].value, "")

    def test_revoked_access_token_stops_working_immediately(self):
        client, _ = self.login()
        sid = RefreshToken(client.cookies[REFRESH_COOKIE].value)["sid"]
        AuthSession.objects.filter(pk=sid).update(revoked_at=timezone.now(), revoked_reason="test")
        response = client.get("/api/auth/session/")
        self.assertEqual(response.status_code, 401)

    def test_single_session_revoke_does_not_touch_current_session(self):
        first, _ = self.login(remote="198.51.100.71")
        second, _ = self.login(client=APIClient(), remote="198.51.100.72", user_agent="Mozilla/5.0 (iPhone) Version/17 Mobile Safari/604.1")
        first_sid = RefreshToken(first.cookies[REFRESH_COOKIE].value)["sid"]
        second_sid = RefreshToken(second.cookies[REFRESH_COOKIE].value)["sid"]

        response = first.delete(f"/api/auth/sessions/{second_sid}/")
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(AuthSession.objects.get(pk=first_sid).revoked_at)
        self.assertIsNotNone(AuthSession.objects.get(pk=second_sid).revoked_at)
        self.assertEqual(second.get("/api/auth/session/").status_code, 401)
        self.assertEqual(first.get("/api/auth/session/").status_code, 200)

    def test_cross_user_session_id_is_not_distinguishable_or_revoked(self):
        client, _ = self.login()
        User = get_user_model()
        other = User.objects.create_user(username="other", password="other-pass-123")
        request = RequestFactory().post("/", HTTP_USER_AGENT="test")
        other_session, _access, _refresh = create_session(other, request)

        response = client.delete(f"/api/auth/sessions/{other_session.pk}/")
        self.assertEqual(response.status_code, 204)
        other_session.refresh_from_db()
        self.assertIsNone(other_session.revoked_at)

    def test_revoke_others_keeps_only_current_session(self):
        current, _ = self.login(remote="198.51.100.73")
        other, _ = self.login(client=APIClient(), remote="198.51.100.74")
        current_sid = RefreshToken(current.cookies[REFRESH_COOKIE].value)["sid"]
        other_sid = RefreshToken(other.cookies[REFRESH_COOKIE].value)["sid"]

        response = current.post("/api/auth/sessions/revoke-others/", format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(AuthSession.objects.get(pk=current_sid).revoked_at)
        self.assertIsNotNone(AuthSession.objects.get(pk=other_sid).revoked_at)

    @override_settings(AUTH_SESSION_FRESH_SECONDS=60)
    def test_stale_session_requires_password_reauth_for_revoke_others(self):
        client, _ = self.login()
        sid = RefreshToken(client.cookies[REFRESH_COOKIE].value)["sid"]
        stale = timezone.now() - timedelta(minutes=10)
        AuthSession.objects.filter(pk=sid).update(last_reauthenticated_at=stale)

        blocked = client.post("/api/auth/sessions/revoke-others/", format="json")
        self.assertEqual(blocked.status_code, 403)

        wrong = client.post("/api/auth/reauth/password/", {"password": "wrong"}, format="json", REMOTE_ADDR="198.51.100.75")
        self.assertEqual(wrong.status_code, 401)
        ok = client.post("/api/auth/reauth/password/", {"password": "session-pass-123"}, format="json", REMOTE_ADDR="198.51.100.75")
        self.assertEqual(ok.status_code, 200, ok.data)
        session = AuthSession.objects.get(pk=sid)
        self.assertGreater(session.last_reauthenticated_at, stale)
        self.assertEqual(client.post("/api/auth/sessions/revoke-others/", format="json").status_code, 200)

    def test_old_refresh_reuse_outside_grace_revokes_whole_session(self):
        client, _ = self.login()
        stolen = client.cookies[REFRESH_COOKIE].value
        sid = RefreshToken(stolen)["sid"]
        self.assertEqual(client.post("/api/auth/refresh/", format="json").status_code, 200)
        AuthSession.objects.filter(pk=sid).update(previous_refresh_valid_until=timezone.now() - timedelta(seconds=1))

        attacker = APIClient()
        attacker.cookies[REFRESH_COOKIE] = stolen
        response = attacker.post("/api/auth/refresh/", format="json")
        self.assertEqual(response.status_code, 401)
        session = AuthSession.objects.get(pk=sid)
        self.assertIsNotNone(session.revoked_at)
        self.assertEqual(session.revoked_reason, "refresh_reuse")
        self.assertEqual(client.get("/api/auth/session/").status_code, 401)

    def test_absolute_session_expiry_invalidates_access(self):
        client, _ = self.login()
        sid = RefreshToken(client.cookies[REFRESH_COOKIE].value)["sid"]
        AuthSession.objects.filter(pk=sid).update(absolute_expires_at=timezone.now() - timedelta(seconds=1))
        response = client.get("/api/auth/session/")
        self.assertEqual(response.status_code, 401)
        session = AuthSession.objects.get(pk=sid)
        self.assertEqual(session.revoked_reason, "absolute_expiry")

    def test_password_reset_contract_can_revoke_all_existing_sessions(self):
        self.login(remote="198.51.100.76")
        self.login(client=APIClient(), remote="198.51.100.77")
        self.assertEqual(AuthSession.objects.filter(user=self.user, revoked_at__isnull=True).count(), 2)
        revoked = revoke_all_user_sessions(self.user, reason="password_reset")
        self.assertEqual(revoked, 2)
        self.assertFalse(AuthSession.objects.filter(user=self.user, revoked_at__isnull=True).exists())


@override_settings(AUTH_SESSION_REFRESH_REUSE_GRACE_SECONDS=5)
class AuthSessionRefreshConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Refresh row-lock concurrency test requires PostgreSQL")
        User = get_user_model()
        self.user = User.objects.create_user(username="race-user", password="race-pass-123")
        request = RequestFactory().post("/", HTTP_USER_AGENT="race test")
        self.session, _access, refresh = create_session(self.user, request)
        self.raw_refresh = str(refresh)

    def _rotate(self):
        close_old_connections()
        try:
            result = rotate_refresh(self.raw_refresh)
            return result.parallel_conflict
        finally:
            close_old_connections()

    def test_parallel_refresh_allows_one_rotation_without_false_revoke(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self._rotate(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        self.session.refresh_from_db()
        self.assertIsNone(self.session.revoked_at)
        self.assertTrue(self.session.current_refresh_jti)
        self.assertTrue(self.session.previous_refresh_jti)
