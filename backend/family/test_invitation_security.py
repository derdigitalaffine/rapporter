from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_identity.service import create_primary_identity

from .invitation_service import issue_invitation, resolve_invitation, rotate_invitation
from .models import Family, FamilyInvitation, Membership


class InvitationSecurityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username="invite-owner",
            password="test-pass-123",
            email="owner@example.com",
        )
        self.target = User.objects.create_user(
            username="invite-target",
            password="test-pass-123",
            email="target@example.com",
        )
        self.family = Family.objects.create(name="Invite Family", slug="invite-family")
        Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Owner",
        )

    def issue(self, *, email="target@example.com"):
        return issue_invitation(
            family=self.family,
            invited_by=self.owner,
            role=Membership.Role.ADULT,
            email=email,
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_member_invite_requires_delivery_email(self):
        client = APIClient()
        client.force_authenticate(self.owner)

        response = client.post(
            "/api/invitations/",
            {"family": str(self.family.pk), "role": Membership.Role.ADULT, "email": ""},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
        self.assertEqual(FamilyInvitation.objects.count(), 0)

    def test_plaintext_token_is_never_kept_at_rest(self):
        invite, token = self.issue()
        invite.refresh_from_db()

        self.assertNotEqual(invite.token, token)
        self.assertRegex(invite.token, r"^[0-9a-f]{64}$")
        self.assertEqual(resolve_invitation(token).pk, invite.pk)

    def test_rotation_invalidates_previous_token_and_keeps_digest_only(self):
        invite, old_token = self.issue()
        old_digest = invite.token

        invite, new_token = rotate_invitation(invite)
        invite.refresh_from_db()

        self.assertNotEqual(new_token, old_token)
        self.assertNotEqual(invite.token, old_digest)
        self.assertNotEqual(invite.token, new_token)
        self.assertRegex(invite.token, r"^[0-9a-f]{64}$")
        self.assertIsNone(resolve_invitation(old_token))
        self.assertEqual(resolve_invitation(new_token).pk, invite.pk)

    def test_owner_endpoints_never_expose_token_or_digest(self):
        invite, _token = self.issue()
        client = APIClient()
        client.force_authenticate(self.owner)

        detail = client.get(f"/api/invitations/{invite.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("token", detail.data)

        renewed = client.post(f"/api/invitations/{invite.pk}/renew/", {}, format="json")
        self.assertEqual(renewed.status_code, 200)
        self.assertNotIn("token", renewed.data)

        listed = client.get("/api/invitations/")
        self.assertEqual(listed.status_code, 200)
        rows = listed.data.get("results", listed.data)
        self.assertTrue(rows)
        self.assertTrue(all("token" not in row for row in rows))

    def test_bound_existing_account_requires_verified_matching_identity(self):
        identity = create_primary_identity(self.target, "target@example.com")
        invite, token = self.issue(email="target@example.com")
        client = APIClient()
        client.force_authenticate(self.target)

        unverified = client.post(f"/api/invite/{token}/accept/", {}, format="json")
        self.assertEqual(unverified.status_code, 403)
        self.assertFalse(Membership.objects.filter(family=self.family, user=self.target).exists())
        invite.refresh_from_db()
        self.assertIsNone(invite.accepted_at)

        identity.verified_at = timezone.now()
        identity.save(update_fields=["verified_at", "updated_at"])

        accepted = client.post(f"/api/invite/{token}/accept/", {}, format="json")
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(Membership.objects.filter(family=self.family, user=self.target).exists())
        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)

    def test_bound_existing_account_rejects_different_verified_identity(self):
        create_primary_identity(self.target, "target@example.com", verified=True)
        invite, token = self.issue(email="someone-else@example.com")
        client = APIClient()
        client.force_authenticate(self.target)

        response = client.post(f"/api/invite/{token}/accept/", {}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Membership.objects.filter(family=self.family, user=self.target).exists())
        invite.refresh_from_db()
        self.assertIsNone(invite.accepted_at)

    def test_direct_legacy_style_save_is_hashed_before_persistence(self):
        raw = "legacy-plaintext-invite-secret"
        invite = FamilyInvitation.objects.create(
            family=self.family,
            token=raw,
            role=Membership.Role.ADULT,
            invited_by=self.owner,
            expires_at=timezone.now() + timedelta(days=7),
        )
        invite.refresh_from_db()

        self.assertNotEqual(invite.token, raw)
        self.assertRegex(invite.token, r"^[0-9a-f]{64}$")
