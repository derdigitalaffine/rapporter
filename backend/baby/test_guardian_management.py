import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APIClient

from family.models import Family, Membership

from .child_identity_service import (
    guardian_settings_for_family,
    replace_child_guardians,
    require_child_guardian,
)
from .models import CareCircleAccess, ManagedChildGuardian
from .pregnancy_service import create_managed_child


User = get_user_model()
PASSWORD = "correct-horse-battery-staple-699"


class GuardianManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-699", password=PASSWORD)
        self.other_owner = User.objects.create_user(username="other-owner-699", password=PASSWORD)
        self.adult = User.objects.create_user(username="adult-699", password=PASSWORD)
        self.outsider = User.objects.create_user(username="outsider-699", password=PASSWORD)
        self.family = Family.objects.create(name="Guardian Family", slug="guardian-family-699")
        self.other_family = Family.objects.create(name="Other Guardian Family", slug="guardian-other-699")
        self.owner_membership = Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.other_owner_membership = Membership.objects.create(
            family=self.family,
            user=self.other_owner,
            role=Membership.Role.OWNER,
            display_name="Sam",
        )
        self.adult_membership = Membership.objects.create(
            family=self.family,
            user=self.adult,
            role=Membership.Role.ADULT,
            display_name="Kim",
        )
        self.outsider_membership = Membership.objects.create(
            family=self.other_family,
            user=self.outsider,
            role=Membership.Role.OWNER,
            display_name="Outsider",
        )
        self.baby = create_managed_child(
            self.owner,
            self.family,
            display_name="Mia",
            birth_date=date(2022, 4, 5),
            client_identity_key=uuid.uuid4(),
        )

    def test_owner_can_bootstrap_first_manager_without_getting_child_read_access(self):
        ManagedChildGuardian.objects.filter(baby=self.baby).delete()
        with self.assertRaises(PermissionDenied):
            require_child_guardian(self.owner, self.baby)

        replace_child_guardians(
            self.owner,
            self.baby.id,
            [{"membership": self.other_owner_membership.id, "can_manage_account": True}],
        )

        with self.assertRaises(PermissionDenied):
            require_child_guardian(self.owner, self.baby)
        require_child_guardian(self.other_owner, self.baby, manage=True)

    def test_adult_without_guardian_cannot_bootstrap_empty_child(self):
        ManagedChildGuardian.objects.filter(baby=self.baby).delete()
        with self.assertRaises(PermissionDenied):
            replace_child_guardians(
                self.adult,
                self.baby.id,
                [{"membership": self.adult_membership.id, "can_manage_account": True}],
            )

    def test_non_guardian_owner_cannot_override_existing_manager(self):
        with self.assertRaises(PermissionDenied):
            replace_child_guardians(
                self.other_owner,
                self.baby.id,
                [{"membership": self.other_owner_membership.id, "can_manage_account": True}],
            )
        require_child_guardian(self.owner, self.baby, manage=True)

    def test_guardian_update_rejects_cross_family_and_requires_a_manager(self):
        with self.assertRaises(ValidationError):
            replace_child_guardians(
                self.owner,
                self.baby.id,
                [{"membership": self.outsider_membership.id, "can_manage_account": True}],
            )
        with self.assertRaises(ValidationError):
            replace_child_guardians(
                self.owner,
                self.baby.id,
                [{"membership": self.owner_membership.id, "can_manage_account": False}],
            )

    def test_legacy_care_circle_guardian_can_seed_then_manage(self):
        ManagedChildGuardian.objects.filter(baby=self.baby).delete()
        CareCircleAccess.objects.create(
            family=self.family,
            membership=self.adult_membership,
            can_log_care=True,
            can_view_growth_development=True,
            is_guardian=True,
        )
        replace_child_guardians(
            self.adult,
            self.baby.id,
            [{"membership": self.adult_membership.id, "can_manage_account": True}],
        )
        require_child_guardian(self.adult, self.baby, manage=True)

    def test_safe_settings_show_permission_metadata_but_no_health_payload(self):
        overview = guardian_settings_for_family(self.other_owner, self.family)
        self.assertEqual(overview["actor_role"], Membership.Role.OWNER)
        self.assertEqual(len(overview["children"]), 1)
        child = overview["children"][0]
        self.assertEqual(child["baby"], str(self.baby.id))
        self.assertEqual(child["membership"], str(self.baby.membership_id))
        self.assertFalse(child["can_manage_guardians"])
        self.assertFalse(child["can_bootstrap_guardians"])
        self.assertNotIn("birth_date", child)
        self.assertNotIn("growth", child)
        self.assertNotIn("development", child)

    def test_owner_safe_settings_expose_bootstrap_only_when_no_manager_exists(self):
        ManagedChildGuardian.objects.filter(baby=self.baby).delete()
        overview = guardian_settings_for_family(self.other_owner, self.family)
        child = overview["children"][0]
        self.assertTrue(child["can_manage_guardians"])
        self.assertTrue(child["can_bootstrap_guardians"])

    def test_safe_settings_endpoint_does_not_unlock_protected_identity(self):
        client = APIClient()
        client.force_authenticate(user=self.other_owner)
        overview = client.get(f"/api/baby/guardian-settings/?family={self.family.id}")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.data["children"][0]["display_name"], "Mia")

        protected = client.get(f"/api/baby/memberships/{self.baby.membership_id}/identity/")
        self.assertEqual(protected.status_code, 403)

    def test_guardian_put_requires_fresh_reauthentication(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.put(
            f"/api/baby/profiles/{self.baby.id}/guardians/",
            {"guardians": [{"membership": str(self.owner_membership.id), "can_manage_account": True}]},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "reauth_required")
