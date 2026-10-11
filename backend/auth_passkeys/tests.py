from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .checks import check_webauthn_configuration
from .models import WebAuthnChallenge, WebAuthnCredential
from .service import PasskeyCeremonyError, _consume_challenge, passkey_config, revoke_credential


@override_settings(
    WEBAUTHN_ENABLED=True,
    APP_URL="https://family.example.test",
    WEBAUTHN_ORIGIN="",
    WEBAUTHN_RP_ID="example.test",
    WEBAUTHN_RP_NAME="FamilyOS",
    WEBAUTHN_CHALLENGE_TTL_SECONDS=300,
)
class PasskeyCoreTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="passkey-user",
            email="passkey@example.test",
            password="a-strong-test-password",
        )

    def test_configuration_uses_app_url_and_parent_rp(self):
        cfg = passkey_config()
        self.assertEqual(cfg.origin, "https://family.example.test")
        self.assertEqual(cfg.rp_id, "example.test")
        self.assertEqual(check_webauthn_configuration(None), [])

    def test_configuration_check_rejects_cross_site_rp(self):
        with override_settings(WEBAUTHN_RP_ID="attacker.example"):
            errors = check_webauthn_configuration(None)
        self.assertEqual(errors[0].id, "auth_passkeys.E005")

    def test_challenge_is_one_time(self):
        challenge = WebAuthnChallenge.objects.create(
            user=self.user,
            ceremony=WebAuthnChallenge.Ceremony.REGISTER,
            challenge=b"x" * 32,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        consumed = _consume_challenge(
            challenge.pk,
            ceremony=WebAuthnChallenge.Ceremony.REGISTER,
            user=self.user,
        )
        self.assertIsNotNone(consumed.consumed_at)
        with self.assertRaises(PasskeyCeremonyError):
            _consume_challenge(
                challenge.pk,
                ceremony=WebAuthnChallenge.Ceremony.REGISTER,
                user=self.user,
            )

    def test_expired_challenge_is_rejected(self):
        challenge = WebAuthnChallenge.objects.create(
            ceremony=WebAuthnChallenge.Ceremony.AUTHENTICATE,
            challenge=b"x" * 32,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        with self.assertRaises(PasskeyCeremonyError):
            _consume_challenge(
                challenge.pk,
                ceremony=WebAuthnChallenge.Ceremony.AUTHENTICATE,
            )

    def test_last_passkey_can_be_revoked_when_password_remains(self):
        credential = WebAuthnCredential.objects.create(
            user=self.user,
            credential_id=b"credential-id",
            public_key=b"public-key",
            name="Laptop",
        )
        revoke_credential(self.user, credential.pk)
        credential.refresh_from_db()
        self.assertIsNotNone(credential.revoked_at)

    def test_last_login_path_is_preserved_for_passwordless_user(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        credential = WebAuthnCredential.objects.create(
            user=self.user,
            credential_id=b"credential-id",
            public_key=b"public-key",
            name="Laptop",
        )
        with self.assertRaises(PasskeyCeremonyError):
            revoke_credential(self.user, credential.pk)
        credential.refresh_from_db()
        self.assertIsNone(credential.revoked_at)
