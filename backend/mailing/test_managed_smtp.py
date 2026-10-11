from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .backends import ManagedRoutingEmailBackend
from .models import ManagedSmtpConfig
from .smtp_config import decrypt_password, effective_mail_config, encrypt_password, public_config


class ManagedSmtpCoreTests(TestCase):
    def test_password_is_encrypted_and_never_returned(self):
        encrypted = encrypt_password("top-secret")
        self.assertNotIn("top-secret", encrypted)
        self.assertEqual(decrypt_password(encrypted), "top-secret")
        ManagedSmtpConfig.objects.create(pk=1, enabled=True, host="smtp.example.test", port=587,
            username="mailer", password_encrypted=encrypted, security="starttls", from_email="mail@example.test")
        payload = public_config()
        self.assertTrue(payload["password_set"])
        self.assertNotIn("password", payload)
        self.assertNotIn("top-secret", str(payload))

    def test_public_config_marks_unreadable_managed_password_unconfigured(self):
        ManagedSmtpConfig.objects.create(pk=1, enabled=True, host="smtp.example.test", port=587,
            username="mailer", password_encrypted="not-valid-fernet", security="starttls",
            from_email="mail@example.test")
        payload = public_config()
        self.assertTrue(payload["password_set"])
        self.assertFalse(payload["configured"])
        self.assertEqual(payload["effective_source"], "superadmin")

    def test_all_managed_security_modes_map_to_django_smtp_flags(self):
        expected = {"starttls": (True, False), "ssl": (False, True), "plain": (False, False)}
        for security, flags in expected.items():
            with self.subTest(security=security):
                ManagedSmtpConfig.objects.update_or_create(pk=1, defaults={
                    "enabled": True, "host": "smtp.example.test", "port": 587, "username": "mailer",
                    "password_encrypted": encrypt_password("secret"), "security": security,
                    "from_email": "mail@example.test",
                })
                cfg = effective_mail_config()
                self.assertEqual((cfg["use_tls"], cfg["use_ssl"]), flags)

    @override_settings(
        EMAIL_BACKEND="mailing.backends.ManagedRoutingEmailBackend",
        EMAIL_ENV_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="env@example.test",
    )
    def test_environment_backend_remains_fallback_when_managed_is_disabled(self):
        ManagedSmtpConfig.objects.create(pk=1, enabled=False, host="managed.example.test", from_email="managed@example.test")
        cfg = effective_mail_config()
        self.assertEqual(cfg["source"], "environment")
        self.assertEqual(cfg["backend"], "django.core.mail.backends.locmem.EmailBackend")
        self.assertEqual(cfg["from_email"], "env@example.test")

    @patch("mailing.backends.get_connection")
    def test_routing_backend_uses_managed_transport_and_sender(self, get_connection):
        target = Mock();target.send_messages.return_value = 1;get_connection.return_value = target
        ManagedSmtpConfig.objects.create(pk=1, enabled=True, host="smtp.example.test", port=465,
            username="mailer", password_encrypted=encrypt_password("secret"), security="ssl",
            from_email="managed@example.test", reply_to="reply@example.test")
        message = EmailMessage("Subject", "Body", "env@example.test", ["to@example.test"])
        sent = ManagedRoutingEmailBackend().send_messages([message])
        self.assertEqual(sent, 1)
        self.assertEqual(message.from_email, "managed@example.test")
        self.assertEqual(message.reply_to, ["reply@example.test"])
        kwargs = get_connection.call_args.kwargs
        self.assertTrue(kwargs["use_ssl"]);self.assertFalse(kwargs["use_tls"])
        self.assertEqual(kwargs["password"], "secret")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ManagedSmtpApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="smtp-admin", email="admin@example.test", password="pass")
        self.user = User.objects.create_user(username="smtp-user", email="user@example.test", password="pass")

    def test_only_superadmin_can_read_config(self):
        regular = APIClient();regular.force_authenticate(self.user)
        self.assertEqual(regular.get("/api/superadmin/smtp/").status_code, 403)
        admin = APIClient();admin.force_authenticate(self.admin)
        response = admin.get("/api/superadmin/smtp/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.data)

    @patch("mailing.superadmin_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_save_keeps_existing_password_when_blank(self, _enforce):
        ManagedSmtpConfig.objects.create(pk=1, enabled=True, host="old.example.test", username="mailer",
            password_encrypted=encrypt_password("keep-me"), from_email="old@example.test")
        client = APIClient();client.force_authenticate(self.admin)
        response = client.put("/api/superadmin/smtp/", {
            "enabled": True, "host": "new.example.test", "port": 587, "username": "mailer", "password": "",
            "security": "starttls", "timeout": 10, "from_email": "new@example.test", "reply_to": ""
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        row = ManagedSmtpConfig.objects.get(pk=1)
        self.assertEqual(decrypt_password(row.password_encrypted), "keep-me")
        self.assertNotIn("keep-me", str(response.data))
        _enforce.assert_called_once()

    @patch("mailing.superadmin_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_explicit_clear_removes_stored_password_while_managed_is_disabled(self, _enforce):
        ManagedSmtpConfig.objects.create(pk=1, enabled=False, host="smtp.example.test", username="mailer",
            password_encrypted=encrypt_password("remove-me"), from_email="mail@example.test")
        client = APIClient();client.force_authenticate(self.admin)
        response = client.put("/api/superadmin/smtp/", {
            "enabled": False, "host": "smtp.example.test", "port": 587, "username": "mailer", "password": "",
            "clear_password": True, "security": "starttls", "timeout": 10,
            "from_email": "mail@example.test", "reply_to": ""
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(ManagedSmtpConfig.objects.get(pk=1).password_encrypted)
        self.assertFalse(response.data["password_set"])
        _enforce.assert_called_once()

    @override_settings(
        EMAIL_BACKEND="mailing.backends.ManagedRoutingEmailBackend",
        EMAIL_ENV_BACKEND="django.core.mail.backends.dummy.EmailBackend",
    )
    @patch("mailing.superadmin_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_test_send_rejects_unconfigured_transport(self, _enforce):
        client = APIClient();client.force_authenticate(self.admin)
        response = client.post("/api/superadmin/smtp/test/", {"recipient": "target@example.test"}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "mail_not_configured")
        _enforce.assert_called_once()

    @patch("mailing.superadmin_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    @patch("mailing.superadmin_views.effective_connection")
    def test_test_send_uses_managed_transport(self, effective_connection, _enforce):
        target = Mock();target.send_messages.return_value = 1;effective_connection.return_value = target
        ManagedSmtpConfig.objects.create(pk=1, enabled=True, host="smtp.example.test", port=587,
            username="mailer", password_encrypted=encrypt_password("secret"), security="starttls",
            from_email="managed@example.test", reply_to="reply@example.test")
        client = APIClient();client.force_authenticate(self.admin)
        response = client.post("/api/superadmin/smtp/test/", {"recipient": "target@example.test"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["accepted"])
        self.assertEqual(response.data["source"], "superadmin")
        self.assertEqual(target.send_messages.call_count, 1)
        message = target.send_messages.call_args.args[0][0]
        self.assertEqual(message.from_email, "managed@example.test")
        self.assertEqual(message.to, ["target@example.test"])
        self.assertEqual(message.reply_to, ["reply@example.test"])
        self.assertNotIn("secret", str(response.data))
        _enforce.assert_called_once()

    @patch("mailing.superadmin_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    @patch("mailing.superadmin_views.effective_connection")
    def test_test_send_redacts_transport_exception(self, effective_connection, _enforce):
        target = Mock();target.send_messages.side_effect = RuntimeError("provider trace contains smtp-password-secret")
        effective_connection.return_value = target
        ManagedSmtpConfig.objects.create(pk=1, enabled=True, host="smtp.example.test", port=587,
            username="mailer", password_encrypted=encrypt_password("secret"), security="starttls",
            from_email="managed@example.test")
        client = APIClient();client.force_authenticate(self.admin)
        response = client.post("/api/superadmin/smtp/test/", {"recipient": "target@example.test"}, format="json")
        self.assertEqual(response.status_code, 502, response.data)
        self.assertEqual(response.data["detail"], "SMTP-Test fehlgeschlagen.")
        self.assertNotIn("smtp-password-secret", str(response.data))
        self.assertIn("code", response.data)
        _enforce.assert_called_once()
