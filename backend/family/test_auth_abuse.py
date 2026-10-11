from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_abuse.models import AuthAbuseBucket

from .models import Family, FamilyInvitation, Membership


@override_settings(AUTH_ABUSE_HMAC_KEY="family-auth-abuse-test-key")
class AuthAbuseIntegrationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@example.test",
            password="owner-password-123",
        )
        self.family = Family.objects.create(name="Family", slug="family")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)

    def test_login_failures_are_rate_limited_without_changing_response_shape(self):
        User = get_user_model()
        User.objects.create_user(
            username="known-user",
            email="known@example.test",
            password="correct-password",
        )
        client = APIClient()
        known = []
        unknown = []
        for _ in range(6):
            known.append(
                client.post(
                    "/api/auth/login/",
                    {"username": "known-user", "password": "wrong-password"},
                    format="json",
                    REMOTE_ADDR="198.51.100.50",
                )
            )
            unknown.append(
                client.post(
                    "/api/auth/login/",
                    {"username": "missing-user", "password": "wrong-password"},
                    format="json",
                    REMOTE_ADDR="198.51.100.51",
                )
            )
        self.assertEqual(known[0].status_code, 401)
        self.assertEqual(unknown[0].status_code, 401)
        self.assertEqual(known[0].data, unknown[0].data)
        self.assertEqual(known[-1].status_code, 429)
        self.assertEqual(unknown[-1].status_code, 429)
        self.assertEqual(known[-1].data["code"], "rate_limited")
        self.assertEqual(unknown[-1].data["code"], "rate_limited")
        self.assertGreaterEqual(known[-1].data["retry_after"], 1)
        self.assertEqual(known[-1]["Retry-After"], str(known[-1].data["retry_after"]))

    def test_successful_login_forgives_identifier_failure_budget(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="recovering-user",
            email="recovering@example.test",
            password="correct-password",
        )
        client = APIClient()
        for _ in range(2):
            response = client.post(
                "/api/auth/login/",
                {"username": user.username, "password": "wrong-password"},
                format="json",
                REMOTE_ADDR="198.51.100.52",
            )
            self.assertEqual(response.status_code, 401)
        response = client.post(
            "/api/auth/login/",
            {"username": user.username, "password": "correct-password"},
            format="json",
            REMOTE_ADDR="198.51.100.52",
        )
        self.assertEqual(response.status_code, 200)
        identifier_buckets = AuthAbuseBucket.objects.filter(
            scope="login.password",
            key_kind="identifier",
        )
        self.assertTrue(identifier_buckets.exists())
        self.assertTrue(all(bucket.count == 0 for bucket in identifier_buckets))

    def test_owner_invite_creation_is_rate_limited_after_authorization(self):
        expires_at = (timezone.now() + timedelta(days=7)).isoformat()
        client = APIClient()
        client.force_authenticate(self.owner)
        responses = [
            client.post(
                "/api/invitations/",
                {
                    "family": str(self.family.id),
                    "role": "adult",
                    "email": f"guest-{index}@example.test",
                    "expires_at": expires_at,
                },
                format="json",
                REMOTE_ADDR="198.51.100.53",
            )
            for index in range(6)
        ]
        self.assertEqual([response.status_code for response in responses[:5]], [201] * 5)
        self.assertEqual(responses[5].status_code, 429)
        self.assertEqual(responses[5].data["code"], "rate_limited")

    def test_unauthorized_invite_attempts_do_not_consume_owner_budget(self):
        User = get_user_model()
        foreign_owner = User.objects.create_user(username="foreign-owner", password="strong-password")
        foreign_family = Family.objects.create(name="Foreign", slug="foreign")
        Membership.objects.create(family=foreign_family, user=foreign_owner, role=Membership.Role.OWNER)
        stranger = User.objects.create_user(username="stranger", password="strong-password")
        expires_at = (timezone.now() + timedelta(days=7)).isoformat()

        client = APIClient()
        client.force_authenticate(stranger)
        responses = [
            client.post(
                "/api/invitations/",
                {
                    "family": str(foreign_family.id),
                    "role": "adult",
                    "email": f"blocked-{index}@example.test",
                    "expires_at": expires_at,
                },
                format="json",
                REMOTE_ADDR="198.51.100.56",
            )
            for index in range(6)
        ]
        self.assertEqual([response.status_code for response in responses], [403] * 6)
        self.assertFalse(AuthAbuseBucket.objects.filter(scope="invite.create").exists())

        owner = APIClient()
        owner.force_authenticate(foreign_owner)
        response = owner.post(
            "/api/invitations/",
            {
                "family": str(foreign_family.id),
                "role": "adult",
                "email": "legitimate@example.com",
                "expires_at": expires_at,
            },
            format="json",
            REMOTE_ADDR="198.51.100.57",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_superadmin_sensitive_mutations_are_rate_limited(self):
        User = get_user_model()
        admin = User.objects.create_superuser(
            username="root",
            email="root@example.com",
            password="super-secure-123",
        )
        client = APIClient()
        login = client.post(
            "/api/superadmin/auth/login/",
            {"identifier": admin.username, "password": "super-secure-123"},
            format="json",
            REMOTE_ADDR="198.51.100.55",
        )
        self.assertEqual(login.status_code, 200)
        responses = []
        for index in range(6):
            requested = Family.Status.SUSPENDED if index % 2 == 0 else Family.Status.ACTIVE
            responses.append(
                client.patch(
                    f"/api/superadmin/families/{self.family.id}/",
                    {"status": requested},
                    format="json",
                    REMOTE_ADDR="198.51.100.55",
                )
            )
        self.assertEqual([response.status_code for response in responses[:5]], [200] * 5)
        self.assertEqual(responses[5].status_code, 429)
        self.assertEqual(responses[5].data["code"], "rate_limited")