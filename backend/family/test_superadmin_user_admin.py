from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from auth_identity.models import EmailIdentity
from auth_identity.service import create_primary_identity
from mailing.models import TransactionalEmail
from telemetry.models import AuditEvent


class SuperadminUserAdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="root", email="root@example.test", password="pass")
        self.regular = User.objects.create_user(username="regular", email="regular@example.test", password="pass")
        self.target = User.objects.create_user(username="target", email="old@example.test", password="pass")
        create_primary_identity(self.target, "old@example.test", verified=True)

    def test_regular_user_cannot_read_or_mutate_global_user_admin(self):
        client = APIClient();client.force_authenticate(self.regular)
        self.assertEqual(client.get("/api/superadmin/users/").status_code, 403)
        self.assertEqual(
            client.post(f"/api/superadmin/users/{self.target.pk}/email-change/", {"email": "new@example.test"}, format="json").status_code,
            403,
        )
        self.assertEqual(
            client.post(f"/api/superadmin/users/{self.target.pk}/email-direct/", {"email": "new@example.test"}, format="json").status_code,
            403,
        )
        self.assertEqual(
            client.post(f"/api/superadmin/users/{self.target.pk}/password-reset-link/", {}, format="json").status_code,
            403,
        )
        self.assertFalse(EmailIdentity.objects.filter(user=self.target, kind=EmailIdentity.Kind.PENDING).exists())

    def test_superadmin_user_list_exposes_identity_state_without_password_material(self):
        client = APIClient();client.force_authenticate(self.admin)
        response = client.get("/api/superadmin/users/?q=target")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["id"], self.target.pk)
        self.assertEqual(row["email"], "old@example.test")
        self.assertTrue(row["email_verified"])
        self.assertTrue(row["can_password_reset"])
        forbidden_secret_fields = {"password", "password_hash", "password_reset_token", "token"}
        self.assertTrue(forbidden_secret_fields.isdisjoint(row.keys()))

    @patch("family.superadmin_user_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_email_change_uses_pending_verification_and_audits_without_replacing_primary(self, enforce):
        client = APIClient();client.force_authenticate(self.admin)
        response = client.post(
            f"/api/superadmin/users/{self.target.pk}/email-change/",
            {"email": "new@example.test"},
            format="json",
        )
        self.assertEqual(response.status_code, 202, response.data)
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "old@example.test")
        primary = EmailIdentity.objects.get(user=self.target, kind=EmailIdentity.Kind.PRIMARY)
        pending = EmailIdentity.objects.get(user=self.target, kind=EmailIdentity.Kind.PENDING)
        self.assertEqual(primary.email, "old@example.test")
        self.assertEqual(pending.email, "new@example.test")
        self.assertIsNotNone(pending.verification_sent_at)
        mail = TransactionalEmail.objects.get(template_key="email.verify", reference_type="email_identity.verify")
        self.assertEqual(mail.recipient, "new@example.test")
        self.assertTrue(AuditEvent.objects.filter(
            event_key="superadmin.user.email_change_requested",
            actor=self.admin,
            actor_class="superadmin",
            target_type="user",
            target_id=str(self.target.pk),
        ).exists())
        enforce.assert_called_once()

    @patch("family.superadmin_user_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_email_change_rejects_address_owned_by_another_identity(self, _enforce):
        User = get_user_model()
        other = User.objects.create_user(username="other", email="taken@example.test", password="pass")
        create_primary_identity(other, "taken@example.test", verified=True)
        client = APIClient();client.force_authenticate(self.admin)
        response = client.post(
            f"/api/superadmin/users/{self.target.pk}/email-change/",
            {"email": "taken@example.test"},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "email_conflict")
        self.assertFalse(EmailIdentity.objects.filter(user=self.target, kind=EmailIdentity.Kind.PENDING).exists())

    @patch("family.superadmin_user_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_direct_email_promotes_matching_pending_and_marks_verified(self, enforce):
        pending = EmailIdentity.objects.create(
            user=self.target,
            kind=EmailIdentity.Kind.PENDING,
            email="new@example.test",
            email_normalized="new@example.test",
        )
        old_primary = EmailIdentity.objects.get(user=self.target, kind=EmailIdentity.Kind.PRIMARY)
        old_version = pending.password_reset_version
        client = APIClient();client.force_authenticate(self.admin)

        response = client.post(
            f"/api/superadmin/users/{self.target.pk}/email-direct/",
            {"email": "new@example.test"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "new@example.test")
        self.assertFalse(EmailIdentity.objects.filter(pk=old_primary.pk).exists())
        promoted = EmailIdentity.objects.get(user=self.target, kind=EmailIdentity.Kind.PRIMARY)
        self.assertEqual(promoted.pk, pending.pk)
        self.assertEqual(promoted.email_normalized, "new@example.test")
        self.assertIsNotNone(promoted.verified_at)
        self.assertGreater(promoted.password_reset_version, old_version)
        self.assertFalse(EmailIdentity.objects.filter(user=self.target, kind=EmailIdentity.Kind.PENDING).exists())
        self.assertTrue(AuditEvent.objects.filter(
            event_key="superadmin.user.email_direct_set",
            actor=self.admin,
            target_type="user",
            target_id=str(self.target.pk),
        ).exists())
        enforce.assert_called_once()

    @patch("family.superadmin_user_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_direct_email_can_repair_inactive_legacy_user(self, _enforce):
        User = get_user_model()
        legacy = User.objects.create_user(username="legacy", email="legacy-old@example.test", password="pass", is_active=False)
        client = APIClient();client.force_authenticate(self.admin)

        response = client.post(
            f"/api/superadmin/users/{legacy.pk}/email-direct/",
            {"email": "legacy-new@example.test"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        legacy.refresh_from_db()
        self.assertEqual(legacy.email, "legacy-new@example.test")
        primary = EmailIdentity.objects.get(user=legacy, kind=EmailIdentity.Kind.PRIMARY)
        self.assertEqual(primary.email, "legacy-new@example.test")
        self.assertIsNotNone(primary.verified_at)
        self.assertFalse(response.data["user"]["can_password_reset"])

    @patch("family.superadmin_user_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_direct_email_rejects_address_owned_by_another_user(self, _enforce):
        User = get_user_model()
        other = User.objects.create_user(username="other", email="taken@example.test", password="pass")
        create_primary_identity(other, "taken@example.test", verified=True)
        client = APIClient();client.force_authenticate(self.admin)

        response = client.post(
            f"/api/superadmin/users/{self.target.pk}/email-direct/",
            {"email": "taken@example.test"},
            format="json",
        )

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "email_conflict")
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "old@example.test")

    @patch("family.superadmin_user_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_password_reset_reuses_canonical_recovery_queue_and_audits(self, enforce):
        client = APIClient();client.force_authenticate(self.admin)
        response = client.post(f"/api/superadmin/users/{self.target.pk}/password-reset/", {}, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        mail = TransactionalEmail.objects.get(template_key="password.reset", reference_type="password_reset")
        self.assertEqual(mail.recipient, "old@example.test")
        self.assertTrue(AuditEvent.objects.filter(
            event_key="superadmin.user.password_reset_requested",
            actor=self.admin,
            actor_class="superadmin",
            target_type="user",
            target_id=str(self.target.pk),
        ).exists())
        enforce.assert_called_once()

    @patch("family.superadmin_user_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_password_reset_requires_verified_primary_identity(self, _enforce):
        User = get_user_model()
        unverified = User.objects.create_user(username="unverified", email="unverified@example.test", password="pass")
        create_primary_identity(unverified, "unverified@example.test", verified=False)
        client = APIClient();client.force_authenticate(self.admin)
        response = client.post(f"/api/superadmin/users/{unverified.pk}/password-reset/", {}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "password_reset_unavailable")
        self.assertFalse(TransactionalEmail.objects.filter(template_key="password.reset", recipient="unverified@example.test").exists())

    @patch("family.superadmin_user_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_reset_link_is_copyable_without_mail_and_new_link_invalidates_old(self, enforce):
        client = APIClient();client.force_authenticate(self.admin)

        first = client.post(f"/api/superadmin/users/{self.target.pk}/password-reset-link/", {}, format="json")
        second = client.post(f"/api/superadmin/users/{self.target.pk}/password-reset-link/", {}, format="json")

        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertTrue(first.data["reset_url"].startswith("http://testserver/reset-password/"))
        self.assertTrue(second.data["reset_url"].startswith("http://testserver/reset-password/"))
        self.assertNotEqual(first.data["reset_url"], second.data["reset_url"])
        self.assertFalse(TransactionalEmail.objects.filter(template_key="password.reset").exists())
        self.assertTrue(AuditEvent.objects.filter(
            event_key="superadmin.user.password_reset_link_created",
            actor=self.admin,
            target_type="user",
            target_id=str(self.target.pk),
        ).exists())

        first_parts = urlparse(first.data["reset_url"]).path.strip("/").split("/")
        second_parts = urlparse(second.data["reset_url"]).path.strip("/").split("/")
        stale = client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": first_parts[-2], "token": first_parts[-1], "password": "A-strong-new-password-417!"},
            format="json",
        )
        self.assertEqual(stale.status_code, 400, stale.data)
        self.assertEqual(stale.data["code"], "invalid_or_expired")

        valid = client.post(
            "/api/auth/password-reset/confirm/",
            {"uid": second_parts[-2], "token": second_parts[-1], "password": "A-strong-new-password-417!"},
            format="json",
        )
        self.assertEqual(valid.status_code, 200, valid.data)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password("A-strong-new-password-417!"))
        self.assertEqual(enforce.call_count, 2)

    @patch("family.superadmin_user_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_reset_link_requires_active_verified_primary(self, _enforce):
        User = get_user_model()
        unverified = User.objects.create_user(username="unverified-link", email="unverified-link@example.test", password="pass")
        create_primary_identity(unverified, "unverified-link@example.test", verified=False)
        inactive = User.objects.create_user(username="inactive-link", email="inactive-link@example.test", password="pass", is_active=False)
        create_primary_identity(inactive, "inactive-link@example.test", verified=True)
        client = APIClient();client.force_authenticate(self.admin)

        unverified_response = client.post(f"/api/superadmin/users/{unverified.pk}/password-reset-link/", {}, format="json")
        inactive_response = client.post(f"/api/superadmin/users/{inactive.pk}/password-reset-link/", {}, format="json")

        self.assertEqual(unverified_response.status_code, 409, unverified_response.data)
        self.assertEqual(inactive_response.status_code, 409, inactive_response.data)
        self.assertNotIn("reset_url", unverified_response.data)
        self.assertNotIn("reset_url", inactive_response.data)
