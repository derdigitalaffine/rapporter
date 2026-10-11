from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership, UserProfile

from .models import BabyProfile, CareCircleAccess, FamilyModuleSetting, ManagedChildGuardian


User = get_user_model()


class ChildProfileManagementTests(TestCase):
    def setUp(self):
        self.guardian = User.objects.create_user(username="guardian-profile", password="correct-horse-battery-staple")
        self.other = User.objects.create_user(username="other-profile", password="correct-horse-battery-staple")
        self.child_user = User.objects.create(username="child-profile-managed", email="", is_active=True)
        self.child_user.set_unusable_password()
        self.child_user.save(update_fields=["password"])
        self.family = Family.objects.create(name="Profile Family", slug="profile-family")
        self.guardian_membership = Membership.objects.create(
            family=self.family, user=self.guardian, role=Membership.Role.OWNER, display_name="Guardian"
        )
        self.other_membership = Membership.objects.create(
            family=self.family, user=self.other, role=Membership.Role.ADULT, display_name="Other"
        )
        self.child_membership = Membership.objects.create(
            family=self.family, user=self.child_user, role=Membership.Role.CHILD, display_name="Mia"
        )
        UserProfile.objects.create(user=self.child_user, birth_year=2022, birth_month=4, birth_day=5)
        FamilyModuleSetting.objects.create(family=self.family, module_key="pregnancy_baby", enabled=True)
        CareCircleAccess.objects.create(
            family=self.family,
            membership=self.guardian_membership,
            can_view_pregnancy=True,
            can_log_care=True,
            can_view_growth_development=True,
            is_guardian=True,
        )
        CareCircleAccess.objects.create(
            family=self.family,
            membership=self.other_membership,
            can_view_pregnancy=True,
            can_log_care=True,
            can_view_growth_development=True,
            is_guardian=False,
        )
        self.baby = BabyProfile.objects.create(
            family=self.family,
            membership=self.child_membership,
            display_name="Mia",
            birth_date=date(2022, 4, 5),
            created_by=self.guardian,
        )
        ManagedChildGuardian.objects.create(
            baby=self.baby, membership=self.guardian_membership, can_manage_account=True
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_guardian_rename_updates_baby_and_membership(self):
        response = self.client_for(self.guardian).patch(
            f"/api/baby/profiles/{self.baby.id}/", {"display_name": "Nora"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.baby.refresh_from_db()
        self.child_membership.refresh_from_db()
        self.assertEqual(self.baby.display_name, "Nora")
        self.assertEqual(self.child_membership.display_name, "Nora")

    def test_non_guardian_manager_cannot_rename(self):
        response = self.client_for(self.other).patch(
            f"/api/baby/profiles/{self.baby.id}/", {"display_name": "Nora"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_requires_both_confirmation_values(self):
        client = self.client_for(self.guardian)
        response = client.delete(
            f"/api/baby/profiles/{self.baby.id}/", {"confirm": "DELETE_CHILD"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(BabyProfile.objects.filter(pk=self.baby.id).exists())

        response = client.delete(
            f"/api/baby/profiles/{self.baby.id}/",
            {"confirm": "DELETE_CHILD", "confirm_name": "Not Mia"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(BabyProfile.objects.filter(pk=self.baby.id).exists())

    def test_confirmed_delete_removes_profile_membership_and_managed_technical_user(self):
        baby_id = self.baby.id
        membership_id = self.child_membership.id
        user_id = self.child_user.id
        response = self.client_for(self.guardian).delete(
            f"/api/baby/profiles/{baby_id}/",
            {"confirm": "DELETE_CHILD", "confirm_name": "Mia"},
            format="json",
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(BabyProfile.objects.filter(pk=baby_id).exists())
        self.assertFalse(Membership.objects.filter(pk=membership_id).exists())
        self.assertFalse(User.objects.filter(pk=user_id).exists())

    def test_confirmed_delete_keeps_activated_user_account(self):
        self.child_user.set_password("a-very-long-child-password-2026")
        self.child_user.save(update_fields=["password"])
        user_id = self.child_user.id
        response = self.client_for(self.guardian).delete(
            f"/api/baby/profiles/{self.baby.id}/",
            {"confirm": "DELETE_CHILD", "confirm_name": "Mia"},
            format="json",
        )
        self.assertEqual(response.status_code, 204)
        self.assertTrue(User.objects.filter(pk=user_id).exists())
        self.assertFalse(Membership.objects.filter(pk=self.child_membership.id).exists())
