from datetime import date
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.family_relationship_models import FamilyRelationship
from family.models import Family, Membership, UserProfile

from .models import BabyProfile, FamilyModuleSetting, ManagedChildGuardian


User = get_user_model()


class FamilyManagedChildTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="family-child-owner", password="correct-horse-battery-staple")
        self.member = User.objects.create_user(username="family-child-member", password="correct-horse-battery-staple")
        self.outsider = User.objects.create_user(username="family-child-outsider", password="correct-horse-battery-staple")
        self.family = Family.objects.create(name="Family Profiles", slug="family-profiles")
        self.other_family = Family.objects.create(name="Other Family", slug="other-family-profiles")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Parent")
        Membership.objects.create(family=self.family, user=self.member, role=Membership.Role.TEEN, display_name="Teen")
        Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER, display_name="Other Parent")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def create_child(self, user=None, family=None, **overrides):
        payload = {
            "family": str((family or self.family).id),
            "display_name": "Mia",
            "birth_date": "2021-05-06",
            "client_identity_key": str(uuid4()),
        }
        payload.update(overrides)
        return self.client_for(user or self.owner).post("/api/baby/managed-children/", payload, format="json")

    def grant_owner_custody(self, baby):
        return FamilyRelationship.objects.create(
            family=self.family,
            child_membership=baby.membership,
            related_membership=self.owner_membership,
            kind=FamilyRelationship.Kind.PARENT,
            has_custody=True,
            status=FamilyRelationship.Status.ACTIVE,
        )

    def test_owner_creates_child_without_baby_module_or_inferred_authority(self):
        self.assertFalse(FamilyModuleSetting.objects.filter(family=self.family, enabled=True).exists())
        response = self.create_child()
        self.assertEqual(response.status_code, 201)
        membership = Membership.objects.get(pk=response.data["membership"])
        baby = BabyProfile.objects.get(pk=response.data["baby"])
        profile = UserProfile.objects.get(user=membership.user)
        self.assertEqual(membership.family, self.family)
        self.assertEqual(membership.role, Membership.Role.CHILD)
        self.assertEqual(membership.display_name, "Mia")
        self.assertEqual(membership.birthday_visibility, Membership.BirthdayVisibility.FULL_DATE)
        self.assertEqual(baby.membership, membership)
        self.assertEqual(baby.birth_date, date(2021, 5, 6))
        self.assertEqual((profile.birth_year, profile.birth_month, profile.birth_day), (2021, 5, 6))
        self.assertEqual(membership.user.email, "")
        self.assertFalse(membership.user.has_usable_password())
        self.assertEqual(response.data["access_state"], "managed")
        self.assertFalse(ManagedChildGuardian.objects.filter(baby=baby).exists())
        self.assertFalse(FamilyRelationship.objects.filter(child_membership=baby.membership).exists())

    def test_non_manager_cannot_create_child(self):
        response = self.create_child(user=self.member)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BabyProfile.objects.filter(family=self.family).exists())

    def test_cross_family_create_is_not_found(self):
        response = self.create_child(user=self.owner, family=self.other_family)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(BabyProfile.objects.filter(family=self.other_family).exists())

    def test_family_profile_read_and_patch_syncs_birthday_for_custodian(self):
        created = self.create_child()
        self.assertEqual(created.status_code, 201)
        baby = BabyProfile.objects.get(pk=created.data["baby"])
        membership = baby.membership
        self.grant_owner_custody(baby)
        client = self.client_for(self.owner)
        read = client.get(f"/api/baby/profiles/{baby.id}/family-profile/")
        self.assertEqual(read.status_code, 200)
        self.assertEqual(set(read.data), {"id", "membership", "display_name", "birth_date"})
        self.assertEqual(read.data["birth_date"], "2021-05-06")
        patched = client.patch(
            f"/api/baby/profiles/{baby.id}/family-profile/",
            {"display_name": "Mia Marie", "birth_date": "2021-05-07"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        baby.refresh_from_db()
        membership.refresh_from_db()
        profile = UserProfile.objects.get(user=membership.user)
        self.assertEqual(baby.display_name, "Mia Marie")
        self.assertEqual(baby.birth_date, date(2021, 5, 7))
        self.assertEqual(membership.display_name, "Mia Marie")
        self.assertEqual((profile.birth_year, profile.birth_month, profile.birth_day), (2021, 5, 7))

    def test_family_members_compat_profile_path_works_for_custodian_without_baby_module(self):
        created = self.create_child()
        baby = BabyProfile.objects.get(pk=created.data["baby"])
        self.grant_owner_custody(baby)
        client = self.client_for(self.owner)
        read = client.get(f"/api/baby/profiles/{baby.id}/")
        self.assertEqual(read.status_code, 200)
        self.assertEqual(set(read.data), {"id", "membership", "display_name", "birth_date"})
        patched = client.patch(
            f"/api/baby/profiles/{baby.id}/",
            {"display_name": "Mia Family", "birth_date": "2021-05-08"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        baby.refresh_from_db()
        profile = UserProfile.objects.get(user=baby.membership.user)
        self.assertEqual(baby.display_name, "Mia Family")
        self.assertEqual(baby.birth_date, date(2021, 5, 8))
        self.assertEqual((profile.birth_year, profile.birth_month, profile.birth_day), (2021, 5, 8))
        baby_rename = client.patch(
            f"/api/baby/profiles/{baby.id}/",
            {"display_name": "Baby module rename"},
            format="json",
        )
        self.assertEqual(baby_rename.status_code, 404)

    def test_non_custodian_cannot_read_or_patch_family_child_profile(self):
        created = self.create_child()
        baby_id = created.data["baby"]
        adult = User.objects.create_user(username="other-adult", password="correct-horse-battery-staple")
        Membership.objects.create(family=self.family, user=adult, role=Membership.Role.ADULT, display_name="Other Adult")
        client = self.client_for(adult)
        self.assertEqual(client.get(f"/api/baby/profiles/{baby_id}/family-profile/").status_code, 403)
        self.assertEqual(client.patch(f"/api/baby/profiles/{baby_id}/family-profile/", {"birth_date": "2020-01-01"}, format="json").status_code, 403)