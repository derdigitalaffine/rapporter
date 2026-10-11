from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from auth_identity.models import EmailIdentity
from auth_identity.service import create_primary_identity
from telemetry.models import AuditEvent

from .models import Family, FamilyInvitation, Membership, UserProfile


ALLOW_SENSITIVE = patch(
    "family.superadmin_user_crud_views._enforce_sensitive_action",
    return_value=SimpleNamespace(allowed=True),
)


class SuperadminUserCrudTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            username="root",
            email="root@example.test",
            password="A-strong-password-471!",
        )
        self.other_admin = User.objects.create_superuser(
            username="backup-root",
            email="backup@example.test",
            password="A-strong-password-472!",
        )
        self.regular = User.objects.create_user(
            username="regular",
            email="regular@example.test",
            password="A-strong-password-473!",
        )
        self.target = User.objects.create_user(
            username="target",
            email="",
            password="A-strong-password-474!",
            first_name="Old",
            last_name="Name",
        )
        create_primary_identity(self.target, "target@example.test", verified=True)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(self.admin)

    def test_non_superadmin_cannot_create_update_or_delete_users(self):
        client = APIClient()
        client.force_authenticate(self.regular)

        create = client.post(
            "/api/superadmin/users/",
            {"username": "blocked", "password": "A-strong-password-475!"},
            format="json",
        )
        update = client.patch(
            f"/api/superadmin/users/{self.target.pk}/",
            {"is_active": False},
            format="json",
        )
        delete = client.delete(
            f"/api/superadmin/users/{self.target.pk}/",
            {"confirm": True, "confirm_username": self.target.username},
            format="json",
        )

        self.assertEqual(create.status_code, 403)
        self.assertEqual(update.status_code, 403)
        self.assertEqual(delete.status_code, 403)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    @ALLOW_SENSITIVE
    def test_create_hashes_password_creates_verified_identity_and_audits(self, _enforce):
        response = self.admin_client.post(
            "/api/superadmin/users/",
            {
                "username": "created-user",
                "email": "created@example.test",
                "first_name": "Created",
                "last_name": "User",
                "password": "A-strong-created-password-471!",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        user = get_user_model().objects.get(username="created-user")
        self.assertTrue(user.check_password("A-strong-created-password-471!"))
        self.assertNotEqual(user.password, "A-strong-created-password-471!")
        identity = EmailIdentity.objects.get(user=user, kind=EmailIdentity.Kind.PRIMARY)
        self.assertEqual(identity.email, "created@example.test")
        self.assertIsNotNone(identity.verified_at)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_key="superadmin.user.created",
                actor=self.admin,
                target_type="user",
                target_id=str(user.pk),
            ).exists()
        )
        self.assertNotIn("password", response.data["user"])
        self.assertNotIn("password_hash", response.data["user"])

    @ALLOW_SENSITIVE
    def test_patch_edits_profile_password_role_and_activation_with_audit(self, _enforce):
        response = self.admin_client.patch(
            f"/api/superadmin/users/{self.target.pk}/",
            {
                "username": "target-renamed",
                "first_name": "New",
                "last_name": "Person",
                "email": "new-target@example.test",
                "password": "A-strong-replacement-471!",
                "is_active": False,
                "is_superuser": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.target.refresh_from_db()
        self.assertEqual(self.target.username, "target-renamed")
        self.assertEqual(self.target.first_name, "New")
        self.assertEqual(self.target.last_name, "Person")
        self.assertFalse(self.target.is_active)
        self.assertTrue(self.target.check_password("A-strong-replacement-471!"))
        self.assertEqual(
            EmailIdentity.objects.get(user=self.target, kind=EmailIdentity.Kind.PRIMARY).email,
            "new-target@example.test",
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_key="superadmin.user.deactivated",
                actor=self.admin,
                target_id=str(self.target.pk),
            ).exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(
                event_key="superadmin.user.updated",
                actor=self.admin,
                target_id=str(self.target.pk),
            ).exists()
        )

        reactivate = self.admin_client.patch(
            f"/api/superadmin/users/{self.target.pk}/",
            {"is_active": True},
            format="json",
        )
        self.assertEqual(reactivate.status_code, 200, reactivate.data)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_key="superadmin.user.reactivated",
                actor=self.admin,
                target_id=str(self.target.pk),
            ).exists()
        )

    @ALLOW_SENSITIVE
    def test_self_deactivate_and_self_delete_are_blocked(self, _enforce):
        deactivate = self.admin_client.patch(
            f"/api/superadmin/users/{self.admin.pk}/",
            {"is_active": False},
            format="json",
        )
        delete = self.admin_client.delete(
            f"/api/superadmin/users/{self.admin.pk}/",
            {"confirm": True, "confirm_username": self.admin.username},
            format="json",
        )

        self.assertEqual(deactivate.status_code, 409, deactivate.data)
        self.assertEqual(deactivate.data["code"], "self_protection")
        self.assertEqual(delete.status_code, 409, delete.data)
        self.assertEqual(delete.data["code"], "self_protection")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertTrue(self.admin.is_superuser)

    @ALLOW_SENSITIVE
    def test_last_active_superadmin_cannot_be_demoted_or_deleted(self, _enforce):
        self.other_admin.is_active = False
        self.other_admin.save(update_fields=["is_active"])

        demote = self.admin_client.patch(
            f"/api/superadmin/users/{self.admin.pk}/",
            {"is_superuser": False},
            format="json",
        )
        self.assertEqual(demote.status_code, 409, demote.data)
        self.assertEqual(demote.data["code"], "self_protection")

        other_client = APIClient()
        other_client.force_authenticate(self.admin)
        target_admin = get_user_model().objects.create_superuser(
            username="temporary-root",
            email="temporary@example.test",
            password="A-strong-password-499!",
            is_active=False,
        )
        delete = other_client.delete(
            f"/api/superadmin/users/{target_admin.pk}/",
            {"confirm": True, "confirm_username": target_admin.username},
            format="json",
        )
        self.assertEqual(delete.status_code, 200, delete.data)

    @ALLOW_SENSITIVE
    def test_purge_requires_double_confirmation_and_deletes_owned_cascades_only(self, _enforce):
        family = Family.objects.create(name="Shared Family", slug="shared-family")
        membership = Membership.objects.create(
            family=family,
            user=self.target,
            role=Membership.Role.ADULT,
            display_name="Target",
        )
        profile = UserProfile.objects.create(user=self.target)
        invitation = FamilyInvitation.objects.create(
            family=family,
            invited_by=self.target,
            email="invitee@example.test",
            expires_at=timezone.now() + timedelta(days=2),
        )

        missing = self.admin_client.delete(
            f"/api/superadmin/users/{self.target.pk}/",
            {"confirm": True},
            format="json",
        )
        wrong = self.admin_client.delete(
            f"/api/superadmin/users/{self.target.pk}/",
            {"confirm": True, "confirm_username": "wrong-user"},
            format="json",
        )
        self.assertEqual(missing.status_code, 409, missing.data)
        self.assertEqual(missing.data["code"], "double_confirmation_required")
        self.assertEqual(wrong.status_code, 409, wrong.data)
        self.assertTrue(get_user_model().objects.filter(pk=self.target.pk).exists())

        target_id = self.target.pk
        deleted = self.admin_client.delete(
            f"/api/superadmin/users/{target_id}/",
            {"confirm": True, "confirm_username": "target"},
            format="json",
        )

        self.assertEqual(deleted.status_code, 200, deleted.data)
        self.assertTrue(deleted.data["deleted"])
        self.assertFalse(get_user_model().objects.filter(pk=target_id).exists())
        self.assertFalse(EmailIdentity.objects.filter(user_id=target_id).exists())
        self.assertFalse(Membership.objects.filter(pk=membership.pk).exists())
        self.assertFalse(UserProfile.objects.filter(pk=profile.pk).exists())
        self.assertTrue(Family.objects.filter(pk=family.pk).exists())
        invitation.refresh_from_db()
        self.assertIsNone(invitation.invited_by_id)
        self.assertTrue(
            AuditEvent.objects.filter(
                event_key="superadmin.user.purged",
                actor=self.admin,
                target_type="user",
                target_id=str(target_id),
            ).exists()
        )
