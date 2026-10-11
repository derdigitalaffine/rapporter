from types import SimpleNamespace
from unittest.mock import patch

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
        self.assertNotIn("password", str(row).lower())

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
