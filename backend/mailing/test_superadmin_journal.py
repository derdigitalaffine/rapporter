from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .service import enqueue_transactional_email


class SuperadminMailJournalTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="mail-admin", email="admin@example.test", password="pass")
        self.regular = User.objects.create_user(username="mail-user", email="user@example.test", password="pass")

    def test_regular_user_cannot_read_mail_journal(self):
        client = APIClient();client.force_authenticate(self.regular)
        self.assertEqual(client.get("/api/superadmin/mail-journal/").status_code, 403)

    def test_mail_journal_redacts_recipient_context_message_key_and_reference(self):
        row = enqueue_transactional_email(
            message_key="password-reset:123:v4",
            template_key="password.reset",
            recipient="secret.person@example.test",
            locale="de",
            context={"action_label": "Passwort zurücksetzen"},
            reference_type="password_reset",
            reference_id="123:4",
        )
        row.attempt_count = 2
        row.last_error_code = "transport"
        row.save(update_fields=["attempt_count", "last_error_code", "updated_at"])

        client = APIClient();client.force_authenticate(self.admin)
        response = client.get("/api/superadmin/mail-journal/?limit=10")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        item = response.data["results"][0]
        self.assertEqual(item["template_key"], "password.reset")
        self.assertEqual(item["status"], "queued")
        self.assertEqual(item["attempt_count"], 2)
        self.assertEqual(item["last_error_code"], "transport")
        self.assertTrue(item["recipient_hint"])
        serialized = str(response.data)
        self.assertNotIn("secret.person@example.test", serialized)
        self.assertNotIn("Passwort zurücksetzen", serialized)
        self.assertNotIn("password-reset:123:v4", serialized)
        self.assertNotIn("123:4", serialized)
        self.assertNotIn("context", item)
        self.assertNotIn("message_key", item)
        self.assertNotIn("reference_type", item)
        self.assertNotIn("reference_id", item)
        self.assertNotIn("recipient", item)
