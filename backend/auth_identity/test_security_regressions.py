from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family, FamilyInvitation, Membership
from mailing.models import TransactionalEmail

from .service import create_primary_identity, pending_identity, verification_token


MAIL_SETTINGS = {
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "DEFAULT_FROM_EMAIL": "FamilyOS <noreply@familyos.test>",
    "APP_URL": "https://familyos.test",
    "AUTH_ABUSE_HMAC_KEY": "identity-security-tests-abuse-key",
}


@override_settings(**MAIL_SETTINGS)
class IdentitySecurityRegressionTests(TestCase):
    def test_email_change_security_notice_uses_verification_request_locale(self):
        user = get_user_model().objects.create_user(
            username="locale-user",
            email="old@example.com",
            password="test-pass-123",
        )
        create_primary_identity(user, "old@example.com", verified=True)
        client = APIClient()
        client.force_authenticate(user)

        change = client.post(
            "/api/auth/email/change/",
            {"email": "new@example.com", "password": "test-pass-123"},
            format="json",
            HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9",
            REMOTE_ADDR="198.51.100.141",
        )
        self.assertEqual(change.status_code, 202, change.data)
        pending = pending_identity(user)
        self.assertIsNotNone(pending)

        verify = APIClient().post(
            "/api/auth/email/verify/",
            {"token": verification_token(pending)},
            format="json",
            HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9",
        )
        self.assertEqual(verify.status_code, 200, verify.data)
        notice = TransactionalEmail.objects.get(
            template_key="email.changed",
            recipient="old@example.com",
        )
        self.assertEqual(notice.locale, "en")

    def test_invite_email_collision_rolls_back_generated_user(self):
        User = get_user_model()
        owner = User.objects.create_user(
            username="owner-security",
            email="owner@example.com",
            password="test-pass-123",
        )
        existing = User.objects.create_user(
            username="existing-member",
            email="collision@example.com",
            password="test-pass-123",
        )
        create_primary_identity(existing, "collision@example.com", verified=True)
        family = Family.objects.create(
            name="Rollback Family",
            slug="identity-rollback-family",
            locale="de",
        )
        Membership.objects.create(
            family=family,
            user=owner,
            role=Membership.Role.OWNER,
        )
        invite = FamilyInvitation.objects.create(
            family=family,
            invited_by=owner,
            role=Membership.Role.ADULT,
            display_name="Collision Member",
            expires_at=timezone.now() + timedelta(days=7),
        )

        before_users = User.objects.count()
        response = APIClient().post(
            f"/api/invite/{invite.token}/register/",
            {
                "email": "collision@example.com",
                "password": "new-member-pass-123",
                "display_name": "Collision Member",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(User.objects.count(), before_users)
        self.assertEqual(User.objects.filter(email="collision@example.com").count(), 1)
        self.assertFalse(User.objects.filter(username__startswith="user_").exists())
        invite.refresh_from_db()
        self.assertIsNone(invite.accepted_at)
        self.assertFalse(
            Membership.objects.filter(family=family, user__email="collision@example.com").exists()
        )
