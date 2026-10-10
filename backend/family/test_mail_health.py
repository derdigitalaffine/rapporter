from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


User = get_user_model()


class SuperadminMailHealthTests(TestCase):
    endpoint = "/api/superadmin/health/mail/"

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="member", password="test-password")
        self.superuser = User.objects.create_superuser(
            username="root",
            email="root@example.com",
            password="test-password",
        )

    def test_public_liveness_remains_public(self):
        response = self.client.get("/api/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "FamilyOS"})

    def test_mail_health_requires_superuser(self):
        anonymous = self.client.get(self.endpoint)
        self.assertIn(anonymous.status_code, {401, 403})

        self.client.force_authenticate(user=self.user)
        member = self.client.get(self.endpoint)
        self.assertEqual(member.status_code, 403)

    def test_superuser_receives_only_redacted_operational_summary(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            set(payload),
            {"configured", "counts", "last_success_at", "latency_seconds", "recent_error_classes"},
        )
        serialized = str(payload).lower()
        for forbidden in ("recipient", "subject", "body", "password", "secret", "root@example.com"):
            self.assertNotIn(forbidden, serialized)

    def test_mail_health_is_read_only(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(self.endpoint, {}, format="json")
        self.assertEqual(response.status_code, 405)
