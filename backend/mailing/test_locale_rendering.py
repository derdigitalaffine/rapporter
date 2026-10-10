from django.test import TestCase, override_settings

from . import service


@override_settings(APP_URL="https://familyos.test")
class TransactionalMailLocaleTests(TestCase):
    def test_english_html_uses_english_language_metadata(self):
        row = service.enqueue_transactional_email(
            message_key="locale-en",
            template_key="password.changed",
            recipient="person@example.com",
            locale="en",
        )
        subject, text, html = service.render_transactional_email(row)
        self.assertEqual(subject, "Password changed")
        self.assertIn("Your FamilyOS password was changed.", text)
        self.assertIn('lang="en"', html)

    def test_default_action_label_follows_message_locale(self):
        service.register_reference_resolver("locale-security", lambda _reference_id: "/account/security")
        english = service.enqueue_transactional_email(
            message_key="locale-action-en",
            template_key="email.verify",
            recipient="english@example.com",
            locale="en",
            reference_type="locale-security",
            reference_id="1",
        )
        german = service.enqueue_transactional_email(
            message_key="locale-action-de",
            template_key="email.verify",
            recipient="german@example.com",
            locale="de",
            reference_type="locale-security",
            reference_id="2",
        )

        _, _, english_html = service.render_transactional_email(english)
        _, _, german_html = service.render_transactional_email(german)

        self.assertIn("Open FamilyOS", english_html)
        self.assertNotIn("FamilyOS öffnen", english_html)
        self.assertIn('lang="en"', english_html)
        self.assertIn("FamilyOS öffnen", german_html)
        self.assertIn('lang="de"', german_html)
