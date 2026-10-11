from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_sessions.models import AuthSession
from auth_sessions.service import SessionUnavailable, active_session_for_token, issue_access_token
from mailing.models import TransactionalEmail

from .password_reset import password_reset_path
from .service import create_primary_identity


MAIL_SETTINGS = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DEFAULT_FROM_EMAIL": "FamilyOS <noreply@familyos.test>",
    "APP_URL": "https://familyos.test",
    "AUTH_ABUSE_HMAC_KEY": "password-reset-tests-abuse-key",
    "PASSWORD_RESET_TIMEOUT": 3600,
    "PASSWORD_RESET_RESEND_COOLDOWN_SECONDS": 60,
}


@override_settings(**MAIL_SETTINGS)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reset-user",
            email="reset@example.com",
            password="Old-FamilyOS-Password-9341!",
        )
        self.identity = create_primary_identity(self.user, "reset@example.com", verified=True)
        self.client = APIClient()

    def request_reset(self, email="reset@example.com", remote_addr="198.51.100.201"):
        return self.client.post(
            "/api/auth/password-reset/request/",
            {"email": email},
            format="json",
            REMOTE_ADDR=remote_addr,
            HTTP_ACCEPT_LANGUAGE="de",
        )

    def current_link_parts(self):
        row = TransactionalEmail.objects.filter(template_key="password.reset").order_by("-created_at").first()
        self.assertIsNotNone(row)
        path = password_reset_path(row.reference_id)
        self.assertTrue(path.startswith("/reset-password/"), path)
        _, route, uid, token = path.split("/", 3)
        self.assertEqual(route, "reset-password")
        return uid, token

    def confirm(self, uid, token, password="New-FamilyOS-Password-5827!"):
        return self.client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "password": password},
            format="json",
            REMOTE_ADDR="198.51.100.202",
            HTTP_ACCEPT_LANGUAGE="de",
        )

    def test_known_and_unknown_addresses_have_identical_public_response(self):
        known = self.request_reset(remote_addr="198.51.100.203")
        unknown = self.request_reset("nobody@example.com", remote_addr="198.51.100.204")

        self.assertEqual(known.status_code, 202, known.data)
        self.assertEqual(unknown.status_code, 202, unknown.data)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(TransactionalEmail.objects.filter(template_key="password.reset").count(), 1)

    def test_unverified_and_disabled_accounts_do_not_leak_status_or_queue_mail(self):
        other = get_user_model().objects.create_user(
            username="unverified-reset-user",
            email="unverified@example.com",
            password="Old-FamilyOS-Password-9341!",
        )
        create_primary_identity(other, "unverified@example.com", verified=False)
        disabled = get_user_model().objects.create_user(
            username="disabled-reset-user",
            email="disabled@example.com",
            password="Old-FamilyOS-Password-9341!",
            is_active=False,
        )
        create_primary_identity(disabled, "disabled@example.com", verified=True)

        unknown = self.request_reset("missing@example.com", remote_addr="198.51.100.205")
        unverified = self.request_reset("unverified@example.com", remote_addr="198.51.100.206")
        inactive = self.request_reset("disabled@example.com", remote_addr="198.51.100.207")

        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(unverified.data, unknown.data)
        self.assertEqual(inactive.data, unknown.data)
        self.assertFalse(TransactionalEmail.objects.filter(template_key="password.reset").exists())

    def test_cooldown_keeps_public_response_stable_and_does_not_flood_outbox(self):
        first = self.request_reset(remote_addr="198.51.100.208")
        second = self.request_reset(remote_addr="198.51.100.209")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.data, second.data)
        self.identity.refresh_from_db()
        self.assertEqual(self.identity.password_reset_version, 1)
        self.assertEqual(TransactionalEmail.objects.filter(template_key="password.reset").count(), 1)

    @override_settings(PASSWORD_RESET_RESEND_COOLDOWN_SECONDS=0)
    def test_new_request_invalidates_older_link(self):
        self.request_reset(remote_addr="198.51.100.210")
        old_uid, old_token = self.current_link_parts()
        self.request_reset(remote_addr="198.51.100.211")
        new_uid, new_token = self.current_link_parts()

        old = self.confirm(old_uid, old_token)
        new = self.confirm(new_uid, new_token)

        self.assertEqual(old.status_code, 400, old.data)
        self.assertEqual(old.data["code"], "invalid_or_expired")
        self.assertEqual(new.status_code, 200, new.data)

    def test_token_is_one_time_and_password_changed_notice_is_queued(self):
        self.request_reset(remote_addr="198.51.100.212")
        uid, token = self.current_link_parts()

        first = self.confirm(uid, token)
        replay = self.confirm(uid, token)

        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(replay.status_code, 400, replay.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-FamilyOS-Password-5827!"))
        notice = TransactionalEmail.objects.get(template_key="password.changed")
        self.assertEqual(notice.recipient, "reset@example.com")
        self.assertIn("Sitzungen", notice.context["details"])

    def test_password_validators_are_applied_without_consuming_valid_link(self):
        self.request_reset(remote_addr="198.51.100.213")
        uid, token = self.current_link_parts()

        weak = self.confirm(uid, token, password="123")
        strong = self.confirm(uid, token, password="Another-Strong-FamilyOS-5827!")

        self.assertEqual(weak.status_code, 400, weak.data)
        self.assertEqual(weak.data["code"], "password_invalid")
        self.assertTrue(weak.data["errors"])
        self.assertEqual(strong.status_code, 200, strong.data)

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_token_is_rejected(self):
        self.request_reset(remote_addr="198.51.100.214")
        uid, token = self.current_link_parts()

        response = self.confirm(uid, token)

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["code"], "invalid_or_expired")

    def test_malformed_uid_is_a_safe_invalid_link(self):
        response = self.confirm("not-a-user", "not-a-token")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["code"], "invalid_or_expired")

    def test_successful_reset_revokes_existing_sessions_server_side(self):
        now = timezone.now()
        session = AuthSession.objects.create(
            user=self.user,
            auth_method=AuthSession.AuthMethod.PASSWORD,
            client_label="Test Browser",
            last_seen_at=now,
            last_reauthenticated_at=now,
            absolute_expires_at=now + timedelta(days=30),
            refresh_expires_at=now + timedelta(days=7),
            current_refresh_jti="before-reset",
        )
        access = issue_access_token(session)
        self.request_reset(remote_addr="198.51.100.215")
        uid, token = self.current_link_parts()

        response = self.confirm(uid, token)

        self.assertEqual(response.status_code, 200, response.data)
        session.refresh_from_db()
        self.assertIsNotNone(session.revoked_at)
        self.assertEqual(session.revoked_reason, "password_reset")
        with self.assertRaises(SessionUnavailable):
            active_session_for_token(access)

    def test_request_rate_limit_applies_to_identifier_and_network(self):
        responses = [self.request_reset(remote_addr="198.51.100.216") for _ in range(4)]
        self.assertEqual([response.status_code for response in responses[:3]], [202, 202, 202])
        self.assertEqual(responses[3].status_code, 429)
        self.assertEqual(responses[3].data["code"], "rate_limited")
