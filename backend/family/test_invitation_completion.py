from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_abuse.service import build_identity_keys, get_policy
from auth_identity.models import EmailIdentity
from mailing.models import TransactionalEmail
from telemetry.models import AuditEvent

from .invitation_audit import record_invite_expired_once
from .invitation_serializers import SafeFamilyInvitationSerializer
from .invitation_service import issue_invitation, resolve_invitation
from .invitation_views import accept_for_user, verified_invite_identity_matches
from .models import Family, FamilyInvitation, Membership


class InvitationCompletionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.inviter = User.objects.create_user(
            username="owner",
            email="owner@example.test",
            password="test-password-123",
        )
        self.family = Family.objects.create(name="Test Family", slug="test-family")
        Membership.objects.create(
            family=self.family,
            user=self.inviter,
            role=Membership.Role.OWNER,
            display_name="Owner",
        )

    def issue(self, *, email="Guest@example.test", role=Membership.Role.GUEST, expires_at=None):
        return issue_invitation(
            family=self.family,
            invited_by=self.inviter,
            role=role,
            email=email,
            display_name="Guest",
            expires_at=expires_at,
        )

    def test_same_family_email_and_role_rotates_existing_invite_case_insensitively(self):
        first, first_token = self.issue(email="Guest@example.test")
        second, second_token = self.issue(email="guest@EXAMPLE.test")

        self.assertEqual(first.pk, second.pk)
        self.assertNotEqual(first_token, second_token)
        self.assertIsNone(resolve_invitation(first_token))
        self.assertEqual(resolve_invitation(second_token).pk, first.pk)
        self.assertEqual(
            FamilyInvitation.objects.filter(
                family=self.family,
                role=Membership.Role.GUEST,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            ).count(),
            1,
        )
        self.assertTrue(
            AuditEvent.objects.filter(event_key="invite.created", target_id=str(first.pk)).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(event_key="invite.resent", target_id=str(first.pk)).exists()
        )
        self.assertEqual(
            AuditEvent.objects.filter(event_key="invite.email_queued", target_id=str(first.pk)).count(),
            2,
        )

    def test_different_role_keeps_distinct_invites(self):
        guest, _ = self.issue(role=Membership.Role.GUEST)
        adult, _ = self.issue(role=Membership.Role.ADULT)
        self.assertNotEqual(guest.pk, adult.pk)

    def test_invitation_mail_context_contains_required_onboarding_details_without_secret(self):
        invite, token = self.issue()
        row = TransactionalEmail.objects.get(
            reference_type="family.invitation",
            reference_id__startswith=f"{invite.pk}:",
        )
        details = row.context["details"]
        self.assertIn(self.family.name, details)
        self.assertIn(self.inviter.username, details)
        self.assertIn("Gast", details)
        self.assertIn("Gültig bis", details)
        self.assertNotIn(invite.email, details)
        self.assertNotIn(token, details)
        self.assertNotIn(invite.token, details)

    def test_resend_policy_has_invite_and_recipient_identity_keys(self):
        policy = get_policy("invite.resend")
        first = build_identity_keys(
            policy,
            identifier="Guest@example.test",
            user=self.inviter,
            family_id=self.family.pk,
            invite_id="invite-one",
        )
        second = build_identity_keys(
            policy,
            identifier="other@example.test",
            user=self.inviter,
            family_id=self.family.pk,
            invite_id="invite-two",
        )
        first_by_kind = {key.kind: key for key in first}
        second_by_kind = {key.kind: key for key in second}
        self.assertIn("identifier", first_by_kind)
        self.assertIn("invite", first_by_kind)
        self.assertNotEqual(first_by_kind["identifier"].digest, second_by_kind["identifier"].digest)
        self.assertNotEqual(first_by_kind["invite"].digest, second_by_kind["invite"].digest)

    def test_serializer_projects_outbox_status_without_exposing_token(self):
        invite, _token = self.issue()
        initial = SafeFamilyInvitationSerializer(invite).data
        self.assertNotIn("token", initial)
        self.assertEqual(initial["delivery_status"], "preparing")
        self.assertIsNone(initial["last_sent_at"])

        row = TransactionalEmail.objects.filter(
            reference_type="family.invitation",
            reference_id__startswith=f"{invite.pk}:",
        ).latest("created_at")
        sent_at = timezone.now()
        row.status = TransactionalEmail.Status.SENT
        row.sent_at = sent_at
        row.save(update_fields=["status", "sent_at", "updated_at"])

        fresh = FamilyInvitation.objects.select_related("family", "invited_by").get(pk=invite.pk)
        delivered = SafeFamilyInvitationSerializer(fresh).data
        self.assertEqual(delivered["delivery_status"], "sent")
        self.assertIsNotNone(delivered["last_sent_at"])
        self.assertTrue(
            AuditEvent.objects.filter(event_key="invite.sent", target_id=str(invite.pk)).exists()
        )

    def test_terminal_mail_failure_is_projected_and_audited_without_recipient_metadata(self):
        invite, _token = self.issue()
        row = TransactionalEmail.objects.filter(
            reference_type="family.invitation",
            reference_id__startswith=f"{invite.pk}:",
        ).latest("created_at")
        row.status = TransactionalEmail.Status.FAILED
        row.last_error_code = "smtp_auth"
        row.save(update_fields=["status", "last_error_code", "updated_at"])

        fresh = FamilyInvitation.objects.select_related("family", "invited_by").get(pk=invite.pk)
        self.assertEqual(SafeFamilyInvitationSerializer(fresh).data["delivery_status"], "failed")
        event = AuditEvent.objects.get(event_key="invite.email_failed", target_id=str(invite.pk))
        self.assertEqual(event.metadata, {"role": Membership.Role.GUEST, "error_class": "smtp_auth"})
        self.assertNotIn("email", event.metadata)

    def test_verified_existing_account_binding_is_case_insensitive(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="existing",
            email="case.user@example.test",
            password="test-password-123",
        )
        EmailIdentity.objects.create(
            user=user,
            kind=EmailIdentity.Kind.PRIMARY,
            email="case.user@example.test",
            email_normalized="case.user@example.test",
            verified_at=timezone.now(),
        )
        invite, _token = self.issue(email="CASE.USER@EXAMPLE.TEST")
        self.assertTrue(verified_invite_identity_matches(invite, user))

    def test_existing_non_guest_member_is_not_downgraded_and_accept_is_audited(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="member",
            email="member@example.test",
            password="test-password-123",
        )
        Membership.objects.create(
            family=self.family,
            user=user,
            role=Membership.Role.ADULT,
            display_name="Member",
        )
        invite, _token = self.issue(email="member@example.test", role=Membership.Role.GUEST)

        membership = accept_for_user(invite, user)
        self.assertEqual(membership.role, Membership.Role.ADULT)
        self.assertTrue(
            AuditEvent.objects.filter(event_key="invite.accepted", target_id=str(invite.pk), actor=user).exists()
        )

    def test_revocation_invalidates_public_token_and_is_audited(self):
        invite, token = self.issue()
        client = APIClient()
        client.force_authenticate(self.inviter)
        revoked = client.delete(f"/api/invitations/{invite.pk}/")
        self.assertEqual(revoked.status_code, 204)
        resolved = resolve_invitation(token)
        self.assertIsNotNone(resolved)
        self.assertFalse(resolved.is_active)
        public = APIClient().get(f"/api/invite/{token}/")
        self.assertEqual(public.status_code, 404)
        self.assertTrue(
            AuditEvent.objects.filter(event_key="invite.revoked", target_id=str(invite.pk), actor=self.inviter).exists()
        )

    def test_invite_list_is_tenant_isolated(self):
        User = get_user_model()
        other_owner = User.objects.create_user(
            username="other-owner",
            email="other-owner@example.test",
            password="test-password-123",
        )
        other_family = Family.objects.create(name="Other Family", slug="other-family")
        Membership.objects.create(
            family=other_family,
            user=other_owner,
            role=Membership.Role.OWNER,
            display_name="Other Owner",
        )
        other_invite, _token = issue_invitation(
            family=other_family,
            invited_by=other_owner,
            role=Membership.Role.GUEST,
            email="other-guest@example.test",
        )
        self.issue()

        client = APIClient()
        client.force_authenticate(self.inviter)
        response = client.get("/api/invitations/")
        self.assertEqual(response.status_code, 200)
        rows = response.data.get("results", response.data)
        self.assertTrue(rows)
        self.assertNotIn(str(other_invite.pk), {str(row["id"]) for row in rows})

    def test_expiry_audit_is_idempotent(self):
        invite, _token = self.issue(expires_at=timezone.now() - timedelta(minutes=1))
        record_invite_expired_once(invite)
        record_invite_expired_once(invite)
        self.assertEqual(
            AuditEvent.objects.filter(event_key="invite.expired", target_id=str(invite.pk)).count(),
            1,
        )
