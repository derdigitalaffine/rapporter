import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from family.family_relationship_models import FamilyRelationship
from family.models import Family, Membership

from .child_identity_service import (
    guardian_settings_for_family,
    replace_child_guardians,
    require_child_guardian,
)
from .models import CareCircleAccess, ManagedChildGuardian
from .pregnancy_service import create_managed_child


User = get_user_model()


class GuardianManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-717", password="test-password")
        self.other_owner = User.objects.create_user(username="other-owner-717", password="test-password")
        self.adult = User.objects.create_user(username="adult-717", password="test-password")
        self.outsider = User.objects.create_user(username="outsider-717", password="test-password")
        self.family = Family.objects.create(name="Custody Family", slug="custody-family-717")
        self.other_family = Family.objects.create(name="Other Family", slug="custody-other-717")
        self.owner_membership = Membership.objects.create(family=self.family,user=self.owner,role=Membership.Role.OWNER,display_name="Alex")
        self.other_owner_membership = Membership.objects.create(family=self.family,user=self.other_owner,role=Membership.Role.OWNER,display_name="Sam")
        self.adult_membership = Membership.objects.create(family=self.family,user=self.adult,role=Membership.Role.ADULT,display_name="Kim")
        self.outsider_membership = Membership.objects.create(family=self.other_family,user=self.outsider,role=Membership.Role.OWNER,display_name="Outsider")
        self.baby = create_managed_child(
            self.owner,self.family,display_name="Mia",birth_date=date(2022,4,5),client_identity_key=uuid.uuid4()
        )

    def custody(self, membership, *, active=True):
        return FamilyRelationship.objects.create(
            family=self.family,
            child_membership=self.baby.membership,
            related_membership=membership,
            kind=FamilyRelationship.Kind.PARENT,
            has_custody=True,
            status=FamilyRelationship.Status.ACTIVE if active else FamilyRelationship.Status.INACTIVE,
        )

    def test_existing_custody_is_effective_without_guardian_backfill(self):
        self.custody(self.owner_membership)
        membership, authority = require_child_guardian(self.owner, self.baby, manage=True)
        self.assertEqual(membership, self.owner_membership)
        self.assertEqual(authority.source, "custody")
        self.assertTrue(authority.can_manage_account)
        self.assertFalse(ManagedChildGuardian.objects.filter(baby=self.baby).exists())

    def test_owner_or_parent_without_custody_has_no_child_authority(self):
        FamilyRelationship.objects.create(
            family=self.family,
            child_membership=self.baby.membership,
            related_membership=self.owner_membership,
            kind=FamilyRelationship.Kind.PARENT,
            is_legal_parent=True,
            has_custody=False,
        )
        with self.assertRaises(PermissionDenied):
            require_child_guardian(self.owner, self.baby)
        with self.assertRaises(PermissionDenied):
            require_child_guardian(self.adult, self.baby)

    def test_inactive_custody_has_no_child_authority(self):
        self.custody(self.owner_membership, active=False)
        with self.assertRaises(PermissionDenied):
            require_child_guardian(self.owner, self.baby)

    def test_new_separate_guardian_grant_is_rejected(self):
        self.custody(self.owner_membership)
        with self.assertRaises(ValidationError):
            replace_child_guardians(
                self.owner,
                self.baby.id,
                [{"membership": self.adult_membership.id, "can_manage_account": True}],
            )
        self.assertFalse(ManagedChildGuardian.objects.filter(baby=self.baby,membership=self.adult_membership).exists())

    def test_legacy_explicit_guardian_remains_compatible_without_becoming_custody(self):
        ManagedChildGuardian.objects.create(
            baby=self.baby,
            membership=self.adult_membership,
            can_manage_account=True,
        )
        require_child_guardian(self.adult, self.baby, manage=True)
        self.assertFalse(
            FamilyRelationship.objects.filter(
                child_membership=self.baby.membership,
                related_membership=self.adult_membership,
                has_custody=True,
            ).exists()
        )

    def test_legacy_care_circle_guardian_can_bootstrap_only_as_compatibility(self):
        CareCircleAccess.objects.create(
            family=self.family,
            membership=self.adult_membership,
            can_log_care=True,
            can_view_growth_development=True,
            is_guardian=True,
        )
        require_child_guardian(self.adult, self.baby, manage=True)
        self.assertTrue(ManagedChildGuardian.objects.filter(baby=self.baby,membership=self.adult_membership).exists())
        self.assertFalse(FamilyRelationship.objects.filter(child_membership=self.baby.membership,related_membership=self.adult_membership,has_custody=True).exists())

    def test_settings_project_custody_as_authority_without_owner_bootstrap(self):
        self.custody(self.owner_membership)
        overview = guardian_settings_for_family(self.owner, self.family)
        child = overview["children"][0]
        self.assertTrue(child["custody_is_authority"])
        self.assertFalse(child["can_bootstrap_guardians"])
        self.assertTrue(child["can_manage_guardians"])
        self.assertEqual(child["guardians"][0]["source"], "custody")
        self.assertTrue(child["guardians"][0]["has_custody"])

    def test_owner_without_custody_cannot_bootstrap_empty_authority(self):
        overview = guardian_settings_for_family(self.other_owner, self.family)
        child = overview["children"][0]
        self.assertFalse(child["can_manage_guardians"])
        self.assertFalse(child["can_bootstrap_guardians"])
        with self.assertRaises(PermissionDenied):
            replace_child_guardians(
                self.other_owner,
                self.baby.id,
                [{"membership": self.other_owner_membership.id, "can_manage_account": True}],
            )