from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .backends import ManagedRoutingEmailBackend
from .models import ManagedSmtpConfig
from .smtp_config import decrypt_password, encrypt_password, public_config


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

    @patch("mailing.superadmin_views._enforce_sensitive_action", return_value=SimpleNamespace(allowed=True))
    def test_test_send_rejects_unconfigured_transport(self, _enforce):
        client = APIClient();client.force_authenticate(self.admin)
        response = client.post("/api/superadmin/smtp/test/", {"recipient": "target@example.test"}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "mail_not_configured")

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
