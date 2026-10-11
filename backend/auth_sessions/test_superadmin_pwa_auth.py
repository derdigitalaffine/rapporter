from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .cookies import ACCESS_COOKIE, ADMIN_ACCESS_COOKIE, ADMIN_REFRESH_COOKIE, REFRESH_COOKIE


@override_settings(AUTH_ABUSE_HMAC_KEY="superadmin-pwa-tests-abuse-key")
class SuperadminPwaAuthTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="root-admin",
            email="root@example.test",
            password="admin-pass-123",
        )
        self.regular = User.objects.create_user(
            username="regular-user",
            email="regular@example.test",
            password="regular-pass-123",
        )

    def admin_login(self, client=None):
        client = client or APIClient()
        response = client.post(
            "/api/superadmin/auth/login/",
            {"identifier": self.admin.username, "password": "admin-pass-123"},
            format="json",
            REMOTE_ADDR="198.51.100.90",
        )
        self.assertEqual(response.status_code, 200, response.data)
        return client, response

    def test_regular_account_cannot_create_admin_session(self):
        client = APIClient()
        response = client.post(
            "/api/superadmin/auth/login/",
            {"identifier": self.regular.username, "password": "regular-pass-123"},
            format="json",
            REMOTE_ADDR="198.51.100.91",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data["detail"], "Anmeldung fehlgeschlagen.")
        self.assertNotIn(ADMIN_ACCESS_COOKIE, client.cookies)
        self.assertNotIn(ADMIN_REFRESH_COOKIE, client.cookies)

    def test_admin_cookie_namespace_is_separate_from_family_session(self):
        client = APIClient()
        normal = client.post(
            "/api/auth/login/",
            {"username": self.admin.username, "password": "admin-pass-123", "legacy": True},
            format="json",
            REMOTE_ADDR="198.51.100.92",
        )
        self.assertEqual(normal.status_code, 200, normal.data)
        normal_access = client.cookies[ACCESS_COOKIE].value
        normal_refresh = client.cookies[REFRESH_COOKIE].value

        _, admin = self.admin_login(client)
        self.assertIn(ADMIN_ACCESS_COOKIE, client.cookies)
        self.assertIn(ADMIN_REFRESH_COOKIE, client.cookies)
        self.assertEqual(client.cookies[ACCESS_COOKIE].value, normal_access)
        self.assertEqual(client.cookies[REFRESH_COOKIE].value, normal_refresh)
        self.assertEqual(client.cookies[ADMIN_ACCESS_COOKIE]["path"], "/api/superadmin/")
        self.assertEqual(admin.data["user"]["username"], self.admin.username)

    def test_family_cookie_cannot_authenticate_superadmin_api(self):
        client = APIClient()
        response = client.post(
            "/api/auth/login/",
            {"username": self.admin.username, "password": "admin-pass-123", "legacy": True},
            format="json",
            REMOTE_ADDR="198.51.100.93",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(client.get("/api/superadmin/users/").status_code, {401, 403})

        self.admin_login(client)
        self.assertEqual(client.get("/api/superadmin/users/").status_code, 200)

    def test_admin_logout_revokes_only_admin_session(self):
        client = APIClient()
        normal = client.post(
            "/api/auth/login/",
            {"username": self.admin.username, "password": "admin-pass-123", "legacy": True},
            format="json",
            REMOTE_ADDR="198.51.100.94",
        )
        self.assertEqual(normal.status_code, 200, normal.data)
        normal_access = client.cookies[ACCESS_COOKIE].value
        self.admin_login(client)

        response = client.post("/api/superadmin/auth/logout/", format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(client.cookies[ADMIN_ACCESS_COOKIE].value, "")
        self.assertEqual(client.cookies[ADMIN_REFRESH_COOKIE].value, "")
        self.assertEqual(client.cookies[ACCESS_COOKIE].value, normal_access)
        self.assertEqual(client.get("/api/auth/session/").status_code, 200)

    def test_admin_reauth_rotates_only_admin_access_cookie(self):
        client = APIClient()
        normal = client.post(
            "/api/auth/login/",
            {"username": self.admin.username, "password": "admin-pass-123", "legacy": True},
            format="json",
            REMOTE_ADDR="198.51.100.95",
        )
        self.assertEqual(normal.status_code, 200, normal.data)
        normal_access = client.cookies[ACCESS_COOKIE].value
        self.admin_login(client)

        response = client.post(
            "/api/superadmin/auth/reauth/password/",
            {"password": "admin-pass-123"},
            format="json",
            REMOTE_ADDR="198.51.100.95",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["reauthenticated"])
        self.assertEqual(client.cookies[ACCESS_COOKIE].value, normal_access)
        self.assertTrue(client.cookies[ADMIN_ACCESS_COOKIE].value)
