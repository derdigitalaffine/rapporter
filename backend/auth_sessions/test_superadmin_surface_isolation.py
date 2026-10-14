from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient, APIRequestFactory, APITestCase

from auth_passkeys.models import WebAuthnChallenge, WebAuthnCredential
from auth_sessions.models import AuthSession
from auth_sessions.service import create_session


@override_settings(
    WEBAUTHN_ENABLED=True,
    WEBAUTHN_ORIGIN="https://example.test",
    WEBAUTHN_RP_ID="example.test",
)
class SuperAdminSurfaceIsolationTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(
            username="surface-admin",
            email="surface-admin@example.test",
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )
        self.factory = APIRequestFactory()

    def session_for(self, surface):
        session, access, _ = create_session(self.user, self.factory.post("/test-session"))
        session.surface = surface
        session.save(update_fields=["surface"])
        return session, access

    @staticmethod
    def client_for(access):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return client

    def test_app_token_is_rejected_by_superadmin_api(self):
        _, access = self.session_for(AuthSession.Surface.APP)
        response = self.client_for(access).get("/api/superadmin/auth/session/")
        self.assertEqual(response.status_code, 401)

    def test_superadmin_token_is_rejected_by_app_api(self):
        _, access = self.session_for(AuthSession.Surface.SUPERADMIN)
        response = self.client_for(access).get("/api/auth/sessions/")
        self.assertEqual(response.status_code, 401)

    def test_superadmin_registration_options_are_context_scoped(self):
        _, access = self.session_for(AuthSession.Surface.SUPERADMIN)
        response = self.client_for(access).post(
            "/api/superadmin/auth/passkeys/register/options/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        challenge = WebAuthnChallenge.objects.get(pk=response.data["challenge_id"])
        self.assertEqual(challenge.context, WebAuthnChallenge.Context.SUPERADMIN)
        self.assertEqual(challenge.user_id, self.user.pk)

    def test_superadmin_passkey_list_hides_app_credentials(self):
        app_key = WebAuthnCredential.objects.create(
            user=self.user,
            surface=WebAuthnCredential.Surface.APP,
            credential_id=b"app-key",
            public_key=b"app-public",
            name="App key",
        )
        admin_key = WebAuthnCredential.objects.create(
            user=self.user,
            surface=WebAuthnCredential.Surface.SUPERADMIN,
            credential_id=b"admin-key",
            public_key=b"admin-public",
            name="Admin key",
        )
        _, access = self.session_for(AuthSession.Surface.SUPERADMIN)
        response = self.client_for(access).get("/api/superadmin/auth/passkeys/")
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(str(admin_key.pk), ids)
        self.assertNotIn(str(app_key.pk), ids)
