from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auth_abuse.models import AuthAbuseBucket

from .models import Family, Membership


@override_settings(AUTH_ABUSE_HMAC_KEY="integration-test-only-abuse-key")
class AuthAbuseIntegrationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="test-pass-123",
        )
        self.family = Family.objects.create(name="Alice Family", slug="abuse-alice-family")
        Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
            display_name="Alice",
        )

    def test_login_failure_is_generic_and_rate_limited(self):
        client = APIClient()
        responses = [
            client.post(
                "/api/auth/login/",
                {"username": "alice", "password": "definitely-wrong"},
                format="json",
                REMOTE_ADDR="198.51.100.50",
            )
            for _ in range(6)
        ]
        self.assertEqual([response.status_code for response in responses[:5]], [401] * 5)
        self.assertEqual(responses[5].status_code, 429)
        self.assertEqual(responses[0].data["detail"], responses[5].data["detail"])
        self.assertEqual(responses[5].data["code"], "rate_limited")
        self.assertGreater(int(responses[5]["Retry-After"]), 0)

    def test_unknown_login_identifier_has_same_failure_shape(self):
        client = APIClient()
        known = client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "wrong"},
            format="json",
            REMOTE_ADDR="198.51.100.51",
        )
        unknown = client.post(
            "/api/auth/login/",
            {"username": "nobody-here", "password": "wrong"},
            format="json",
            REMOTE_ADDR="198.51.100.52",
        )
        self.assertEqual(known.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(known.data, unknown.data)

    def test_successful_login_forgives_identifier_specific_counters(self):
        client = APIClient()
        response = client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "test-pass-123"},
            format="json",
            REMOTE_ADDR="198.51.100.53",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuthAbuseBucket.objects.filter(
                scope="login.password",
                key_kind="identifier",
                count=0,
                blocked_until__isnull=True,
            ).exists()
        )

    def test_invitation_creation_is_limited_per_actor_and_family(self):
        client = APIClient()
        client.force_authenticate(self.user)
        responses = []
        for index in range(6):
            responses.append(
                client.post(
                    "/api/invitations/",
                    {
                        "family": str(self.family.id),
                        "role": "adult",
                        "email": f"invite-{index}@example.com",
                        "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
                    },
                    format="json",
                    REMOTE_ADDR="198.51.100.54",
                )
            )
        self.assertEqual([response.status_code for response in responses[:5]], [201] * 5)
        self.assertEqual(responses[5].status_code, 429)
        self.assertEqual(responses[5].data["code"], "rate_limited")

    def test_superadmin_sensitive_mutations_are_rate_limited(self):
        User = get_user_model()
        admin = User.objects.create_superuser(
            username="root",
            email="root@example.com",
            password="super-secure-123",
        )
        client = APIClient()
        client.force_authenticate(admin)
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
