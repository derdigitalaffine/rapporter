from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family, FamilyInvitation, Membership
from mailing.models import TransactionalEmail

from .models import EmailIdentity
from .service import (
    EmailConflictError,
    create_primary_identity,
    normalize_email,
    pending_identity,
    primary_identity,
    queue_verification,
    request_pending_email,
    verification_token,
)


MAIL_SETTINGS = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DEFAULT_FROM_EMAIL": "FamilyOS <noreply@familyos.test>",
    "APP_URL": "https://familyos.test",
    "AUTH_ABUSE_HMAC_KEY": "identity-tests-abuse-key",
}


@override_settings(**MAIL_SETTINGS)
class EmailIdentityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="legacy-alice",
            email="Alice@Example.com",
            password="test-pass-123",
            first_name="Alice",
        )
        self.client = APIClient()

    def test_normalization_preserves_plus_and_dots_but_is_case_insensitive(self):
        self.assertEqual(normalize_email(" Person.Name+tag@Example.COM "), "person.name+tag@example.com")
        self.assertNotEqual(
            normalize_email("person.name+tag@example.com"),
            normalize_email("personname@example.com"),
        )

    def test_normalized_identity_is_globally_unique(self):
        create_primary_identity(self.user, "Alice@Example.com")
        other = get_user_model().objects.create_user(
            username="other",
            email="",
            password="test-pass-123",
        )
        with self.assertRaises(EmailConflictError):
            create_primary_identity(other, "alice@example.COM")

    def test_email_login_succeeds_and_username_login_is_closed_after_migration(self):
        create_primary_identity(self.user, "Alice@Example.com", verified=True)
        response = self.client.post(
            "/api/auth/login/",
            {"email": "ALICE@example.com", "password": "test-pass-123"},
            format="json",
            REMOTE_ADDR="198.51.100.101",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["authenticated"])
        self.assertTrue(response.data["email_verified"])

        legacy = APIClient().post(
            "/api/auth/login/",
            {"username": "legacy-alice", "password": "test-pass-123"},
            format="json",
            REMOTE_ADDR="198.51.100.102",
        )
        self.assertEqual(legacy.status_code, 401)

    def test_unknown_and_wrong_email_have_same_public_response(self):
        create_primary_identity(self.user, "alice@example.com")
        known = APIClient().post(
            "/api/auth/login/",
            {"email": "alice@example.com", "password": "wrong-password"},
            format="json",
            REMOTE_ADDR="198.51.100.103",
        )
        unknown = APIClient().post(
            "/api/auth/login/",
            {"email": "nobody@example.com", "password": "wrong-password"},
            format="json",
            REMOTE_ADDR="198.51.100.104",
        )
        self.assertEqual(known.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(known.data, unknown.data)

    def test_legacy_account_without_identity_can_still_login(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": "legacy-alice", "password": "test-pass-123"},
            format="json",
            REMOTE_ADDR="198.51.100.105",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["email_action_required"])

    def test_verification_is_idempotent(self):
        identity = queue_verification(create_primary_identity(self.user, "alice@example.com"))
        token = verification_token(identity)
        first = self.client.post("/api/auth/email/verify/", {"token": token}, format="json")
        second = self.client.post("/api/auth/email/verify/", {"token": token}, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertTrue(first.data["changed"])
        self.assertFalse(second.data["changed"])
        identity.refresh_from_db()
        self.assertIsNotNone(identity.verified_at)

    @override_settings(EMAIL_VERIFICATION_MAX_AGE_SECONDS=-1)
    def test_expired_verification_token_is_rejected(self):
        identity = queue_verification(create_primary_identity(self.user, "alice@example.com"))
        response = self.client.post(
            "/api/auth/email/verify/",
            {"token": verification_token(identity)},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_resend_has_cooldown_and_uses_central_abuse_scope(self):
        identity = create_primary_identity(self.user, "alice@example.com")
        self.client.force_authenticate(self.user)
        first = self.client.post(
            "/api/auth/email/verification/resend/",
            {"target": "primary"},
            format="json",
            REMOTE_ADDR="198.51.100.106",
        )
        second = self.client.post(
            "/api/auth/email/verification/resend/",
            {"target": "primary"},
            format="json",
            REMOTE_ADDR="198.51.100.106",
        )
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 429)
        identity.refresh_from_db()
        self.assertEqual(identity.verification_version, 1)

    def test_email_change_is_pending_until_verified_and_notifies_old_verified_address(self):
        old = create_primary_identity(self.user, "alice@example.com", verified=True)
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/auth/email/change/",
            {"email": "new@example.com", "password": "test-pass-123"},
            format="json",
            REMOTE_ADDR="198.51.100.107",
        )
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(primary_identity(self.user).pk, old.pk)
        pending = pending_identity(self.user)
        self.assertEqual(pending.email_normalized, "new@example.com")

        verify = APIClient().post(
            "/api/auth/email/verify/",
            {"token": verification_token(pending)},
            format="json",
        )
        self.assertEqual(verify.status_code, 200, verify.data)
        current = primary_identity(self.user)
        self.assertEqual(current.email_normalized, "new@example.com")
        self.assertIsNotNone(current.verified_at)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertTrue(
            TransactionalEmail.objects.filter(
                template_key="email.changed",
                recipient="alice@example.com",
            ).exists()
        )

    def test_email_change_rejects_address_owned_by_another_account(self):
        create_primary_identity(self.user, "alice@example.com", verified=True)
        other = get_user_model().objects.create_user(
            username="other",
            email="other@example.com",
            password="test-pass-123",
        )
        create_primary_identity(other, "other@example.com", verified=True)
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/auth/email/change/",
            {"email": "OTHER@example.com", "password": "test-pass-123"},
            format="json",
            REMOTE_ADDR="198.51.100.108",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(pending_identity(self.user))

    def test_invite_registration_needs_no_username_and_queues_verification(self):
        User = get_user_model()
        owner = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="test-pass-123",
        )
        family = Family.objects.create(name="Invite Family", slug="identity-invite-family", locale="en")
        Membership.objects.create(family=family, user=owner, role=Membership.Role.OWNER)
        invite = FamilyInvitation.objects.create(
            family=family,
            invited_by=owner,
            role=Membership.Role.ADULT,
            email="new.member@example.com",
            display_name="New Member",
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client.post(
            f"/api/invite/{invite.token}/register/",
            {
                "email": "NEW.member@Example.com",
                "password": "new-member-pass-123",
                "display_name": "New Member",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="new.member@example.com")
        self.assertTrue(user.username.startswith("user_"))
        identity = primary_identity(user)
        self.assertIsNotNone(identity)
        self.assertIsNone(identity.verified_at)
        self.assertTrue(Membership.objects.filter(family=family, user=user).exists())
        self.assertTrue(
            TransactionalEmail.objects.filter(
                template_key="email.verify",
                recipient="new.member@example.com",
            ).exists()
        )
