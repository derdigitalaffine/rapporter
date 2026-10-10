import smtplib
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import TransactionalEmail
from . import service


MAIL_SETTINGS = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DEFAULT_FROM_EMAIL": "FamilyOS <noreply@familyos.test>",
    "APP_URL": "https://familyos.test",
    "EMAIL_REPLY_TO": "",
}


@override_settings(**MAIL_SETTINGS)
class TransactionalMailTests(TestCase):
    def enqueue(self, key="mail-1", **kwargs):
        return service.enqueue_transactional_email(
            message_key=key,
            template_key=kwargs.pop("template_key", "email.verify"),
            recipient=kwargs.pop("recipient", "Person@Example.com"),
            locale=kwargs.pop("locale", "de"),
            context=kwargs.pop("context", {"details": "Sicherer Hinweis"}),
            **kwargs,
        )

    def test_enqueue_is_idempotent_and_recipient_domain_is_normalized(self):
        first = self.enqueue()
        second = self.enqueue(recipient="Person@example.COM")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(TransactionalEmail.objects.count(), 1)
        first.refresh_from_db()
        self.assertEqual(first.recipient, "Person@example.com")
        self.assertEqual(len(first.recipient_hash), 64)
        self.assertNotIn("Person@example.com", first.recipient_hash)

    def test_local_part_case_is_part_of_delivery_semantics(self):
        key = "local-case"
        self.enqueue(key=key, recipient="Person@example.com")
        with self.assertRaises(service.IdempotencyConflictError):
            self.enqueue(key=key, recipient="person@example.com")

    def test_message_key_conflict_rejects_different_delivery_semantics(self):
        cases = (
            ("recipient", {"recipient": "other@example.com"}),
            ("template", {"template_key": "password.changed"}),
            ("locale", {"locale": "en"}),
            ("reference", {"reference_type": "security", "reference_id": "42"}),
        )
        for suffix, changed in cases:
            with self.subTest(suffix=suffix):
                key = f"conflict-{suffix}"
                self.enqueue(key=key)
                with self.assertRaises(service.IdempotencyConflictError):
                    self.enqueue(key=key, **changed)
        self.assertEqual(TransactionalEmail.objects.count(), len(cases))

    def test_identical_enqueue_remains_idempotent_after_payload_cleanup(self):
        row = self.enqueue(key="sent-idempotent")
        self.assertTrue(service.process_one_transactional_email())
        row.refresh_from_db()
        self.assertEqual(row.recipient, "")
        again = self.enqueue(key="sent-idempotent", recipient="Person@example.com")
        self.assertEqual(again.pk, row.pk)
        self.assertEqual(TransactionalEmail.objects.count(), 1)

    def test_sensitive_context_keys_are_rejected(self):
        for key in ("reset_token", "password", "webauthn_challenge", "client_secret", "authorization"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.enqueue(key=f"blocked-{key}", context={key: "do-not-store"})

    def test_locale_templates_render_without_external_assets(self):
        row = self.enqueue(locale="en", template_key="password.changed")
        subject, text, html = service.render_transactional_email(row)
        self.assertEqual(subject, "Password changed")
        self.assertIn("Your FamilyOS password was changed.", text)
        self.assertIn("FamilyOS", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_reference_resolver_builds_only_same_app_relative_urls(self):
        service.register_reference_resolver("security-test", lambda _id: "/account/security")
        row = self.enqueue(reference_type="security-test", reference_id="42", context={"action_label": "Öffnen"})
        _, text, html = service.render_transactional_email(row)
        self.assertIn("https://familyos.test/account/security", text)
        self.assertIn("https://familyos.test/account/security", html)

        service.register_reference_resolver("external-test", lambda _id: "https://evil.example/phish")
        external = self.enqueue(key="mail-external", reference_type="external-test", reference_id="1")
        _, external_text, _ = service.render_transactional_email(external)
        self.assertNotIn("evil.example", external_text)

    def test_success_clears_recipient_and_render_context_immediately(self):
        row = self.enqueue()
        self.assertTrue(service.process_one_transactional_email())
        row.refresh_from_db()
        self.assertEqual(row.status, TransactionalEmail.Status.SENT)
        self.assertEqual(row.recipient, "")
        self.assertEqual(row.context, {})
        self.assertIsNotNone(row.payload_cleared_at)
        self.assertIsNotNone(row.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["Person@example.com"])
        self.assertTrue(mail.outbox[0].extra_headers["Message-ID"].startswith("<"))

    def test_transport_failure_retries_with_redacted_error_class_and_keeps_payload(self):
        row = self.enqueue()
        with patch("mailing.service.EmailMultiAlternatives.send", side_effect=OSError("smtp secret host detail")):
            self.assertTrue(service.process_one_transactional_email())
        row.refresh_from_db()
        self.assertEqual(row.status, TransactionalEmail.Status.RETRY)
        self.assertEqual(row.last_error_code, "transport")
        self.assertNotIn("secret", row.last_error_code)
        self.assertGreater(row.next_attempt_at, timezone.now())
        self.assertEqual(row.recipient, "Person@example.com")
        self.assertEqual(row.context, {"details": "Sicherer Hinweis"})
        self.assertIsNone(row.payload_cleared_at)

    def test_recipient_rejection_is_permanent_and_clears_delivery_payload(self):
        row = self.enqueue()
        error = smtplib.SMTPRecipientsRefused({"Person@example.com": (550, b"private provider text")})
        with patch("mailing.service.EmailMultiAlternatives.send", side_effect=error):
            service.process_one_transactional_email()
        row.refresh_from_db()
        self.assertEqual(row.status, TransactionalEmail.Status.FAILED)
        self.assertEqual(row.last_error_code, "recipient_rejected")
        self.assertNotIn("private", row.last_error_code)
        self.assertEqual(row.recipient, "")
        self.assertEqual(row.context, {})
        self.assertIsNotNone(row.payload_cleared_at)

    def test_expired_worker_lease_is_reclaimed_below_attempt_limit(self):
        row = self.enqueue()
        row.status = TransactionalEmail.Status.SENDING
        row.lease_expires_at = timezone.now() - timedelta(seconds=1)
        row.lease_token = "11111111-1111-1111-1111-111111111111"
        row.save(update_fields=["status", "lease_expires_at", "lease_token"])
        claimed = service.claim_due_email()
        self.assertEqual(claimed.pk, row.pk)
        self.assertNotEqual(str(claimed.lease_token), "11111111-1111-1111-1111-111111111111")
        self.assertEqual(claimed.attempt_count, 1)

    def test_expired_worker_lease_at_attempt_limit_is_terminal_not_reclaimed(self):
        row = self.enqueue(key="exhausted-crash")
        row.status = TransactionalEmail.Status.SENDING
        row.attempt_count = service.MAX_ATTEMPTS
        row.lease_expires_at = timezone.now() - timedelta(seconds=1)
        row.lease_token = "22222222-2222-2222-2222-222222222222"
        row.save(update_fields=["status", "attempt_count", "lease_expires_at", "lease_token"])

        self.assertIsNone(service.claim_due_email())
        row.refresh_from_db()
        self.assertEqual(row.status, TransactionalEmail.Status.FAILED)
        self.assertEqual(row.attempt_count, service.MAX_ATTEMPTS)
        self.assertEqual(row.last_error_code, "attempts_exhausted")
        self.assertIsNone(row.lease_token)
        self.assertIsNone(row.lease_expires_at)
        self.assertEqual(row.recipient, "")
        self.assertEqual(row.context, {})
        self.assertIsNotNone(row.payload_cleared_at)

    def test_two_worker_claims_do_not_claim_same_message(self):
        first = self.enqueue(key="worker-1")
        second = self.enqueue(key="worker-2")
        claim_one = service.claim_due_email()
        claim_two = service.claim_due_email()
        self.assertEqual({claim_one.pk, claim_two.pk}, {first.pk, second.pk})
        self.assertNotEqual(claim_one.pk, claim_two.pk)

    def test_health_summary_contains_only_aggregate_operational_data(self):
        self.enqueue()
        service.process_one_transactional_email()
        summary = service.mail_health_summary()
        self.assertTrue(summary["configured"])
        self.assertEqual(summary["counts"][TransactionalEmail.Status.SENT], 1)
        self.assertIsNotNone(summary["last_success_at"])
        serialized = str(summary)
        self.assertNotIn("Person@example.com", serialized)
        self.assertNotIn("Sicherer Hinweis", serialized)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="",
    DEFAULT_FROM_EMAIL="FamilyOS <noreply@example.com>",
)
class MailSystemCheckTests(TestCase):
    def test_smtp_without_host_is_reported_by_django_check(self):
        from mailing.checks import mailing_configuration_checks

        ids = {message.id for message in mailing_configuration_checks(None)}
        self.assertIn("mailing.E002", ids)
