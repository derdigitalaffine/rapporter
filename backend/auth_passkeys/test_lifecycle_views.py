import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_identity.models import EmailIdentity
from mailing.models import TransactionalEmail
from telemetry.models import AuditEvent

from .models import WebAuthnCredential
from .service import PasskeyCeremonyError


@override_settings(
    WEBAUTHN_ENABLED=True,
    APP_URL="https://family.example.test",
    WEBAUTHN_ORIGIN="https://family.example.test",
    WEBAUTHN_RP_ID="example.test",
)
class PasskeyLifecycleViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="passkey-lifecycle",
            email="passkey@example.test",
            password="a-strong-test-password",
        )
        EmailIdentity.objects.create(
            user=self.user,
            kind=EmailIdentity.Kind.PRIMARY,
            email="passkey@example.test",
            email_normalized="passkey@example.test",
            verified_at=timezone.now(),
        )
        self.client = APIClient()

    def credential(self, suffix=b"one"):
        return WebAuthnCredential.objects.create(
            user=self.user,
            credential_id=b"credential-" + suffix,
            public_key=b"public-key-" + suffix,
            name="Laptop",
        )

    def test_registration_queues_security_mail_and_audit(self):
        credential = self.credential()
        self.client.force_authenticate(self.user)
        with (
            patch("auth_passkeys.views.require_fresh_session"),
            patch("auth_passkeys.views._enforce", return_value=None),
            patch("auth_passkeys.views.complete_registration", return_value=credential),
        ):
            response = self.client.post(
                "/api/auth/passkeys/registration/verify/",
                {"challenge_id": "challenge", "credential": {}, "name": "Laptop", "locale": "en"},
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        event = AuditEvent.objects.get(event_key="auth.passkey.registered")
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.target_type, "passkey")
        self.assertEqual(event.target_id, str(credential.pk))
        mail = TransactionalEmail.objects.get(message_key=f"passkey-added:{credential.pk}")
        self.assertEqual(mail.template_key, "passkey.added")
        self.assertEqual(mail.locale, "en")
        self.assertEqual(mail.recipient, "passkey@example.test")

    def test_removal_revokes_credential_and_queues_security_mail_and_audit(self):
        credential = self.credential(b"remove")
        self.client.force_authenticate(self.user)
        with patch("auth_passkeys.views.require_fresh_session"):
            response = self.client.delete(
                f"/api/auth/passkeys/{credential.pk}/",
                {"locale": "de"},
                format="json",
            )

        self.assertEqual(response.status_code, 204)
        credential.refresh_from_db()
        self.assertIsNotNone(credential.revoked_at)
        event = AuditEvent.objects.get(event_key="auth.passkey.removed")
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.target_id, str(credential.pk))
        self.assertEqual(event.reason, "user_request")
        mail = TransactionalEmail.objects.get(message_key=f"passkey-removed:{credential.pk}")
        self.assertEqual(mail.template_key, "passkey.removed")
        self.assertEqual(mail.locale, "de")

    def test_successful_passkey_login_is_counted_as_canonical_auth_event(self):
        credential = self.credential(b"login")
        session_id = uuid.uuid4()
        session = SimpleNamespace(pk=session_id)
        with (
            patch("auth_passkeys.views._enforce", return_value=None),
            patch(
                "auth_passkeys.views.complete_authentication",
                return_value=(credential, session, object(), object()),
            ),
            patch("auth_passkeys.views.forgive"),
            patch("auth_passkeys.views.serialize_session", return_value={"id": str(session_id)}),
            patch("auth_passkeys.views.set_token_cookies", side_effect=lambda response, *_args: response),
        ):
            response = self.client.post(
                "/api/auth/passkeys/authentication/verify/",
                {"challenge_id": "challenge", "credential": {}},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        event = AuditEvent.objects.get(event_key="auth.login.succeeded")
        self.assertEqual(event.actor_id, self.user.pk)
        self.assertEqual(event.target_type, "session")
        self.assertEqual(event.target_id, str(session_id))
        self.assertEqual(event.metadata, {"auth_method": "passkey"})

    def test_failed_passkey_login_is_audited_without_identifier_material(self):
        with (
            patch("auth_passkeys.views._enforce", return_value=None),
            patch("auth_passkeys.views.complete_authentication", side_effect=PasskeyCeremonyError()),
        ):
            response = self.client.post(
                "/api/auth/passkeys/authentication/verify/",
                {"challenge_id": "challenge", "credential": {"id": "not-secret-in-audit"}},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        event = AuditEvent.objects.get(event_key="auth.login.failed")
        self.assertIsNone(event.actor_id)
        self.assertEqual(event.actor_class, "system")
        self.assertEqual(event.metadata, {"auth_method": "passkey"})
        self.assertNotIn("not-secret-in-audit", str(event.metadata))
