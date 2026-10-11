from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership, UserProfile

from .models import BabyProfile, ManagedChildGuardian


User = get_user_model()


class ChildIdentityMembershipLookupTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="guardian-lookup", password="correct-horse-battery-staple")
        self.other = User.objects.create_user(username="member-lookup", password="correct-horse-battery-staple")
        self.outsider = User.objects.create_user(username="outsider-lookup", password="correct-horse-battery-staple")
        self.child_user = User.objects.create(username="child-lookup", email="", is_active=True)
        self.child_user.set_unusable_password()
        self.child_user.save(update_fields=["password"])
        self.family = Family.objects.create(name="Lookup Family", slug="lookup-family")
        self.other_family = Family.objects.create(name="Outside Family", slug="outside-family")
        self.owner_membership = Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Guardian")
        Membership.objects.create(family=self.family, user=self.other, role=Membership.Role.ADULT, display_name="Member")
        Membership.objects.create(family=self.other_family, user=self.outsider, role=Membership.Role.OWNER, display_name="Outsider")
        self.child_membership = Membership.objects.create(family=self.family, user=self.child_user, role=Membership.Role.CHILD, display_name="Mia")
        UserProfile.objects.create(user=self.child_user, birth_year=2022, birth_month=4, birth_day=5)
        self.baby = BabyProfile.objects.create(
            family=self.family,
            membership=self.child_membership,
            display_name="Mia",
            birth_date=date(2022, 4, 5),
            created_by=self.owner,
        )
        ManagedChildGuardian.objects.create(baby=self.baby, membership=self.owner_membership, can_manage_account=True)

    def get_identity(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client.get(f"/api/baby/memberships/{self.child_membership.id}/identity/")

    def test_guardian_resolves_child_identity_without_health_payload(self):
        response = self.get_identity(self.owner)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["baby"], str(self.baby.id))
        self.assertEqual(response.data["membership"], str(self.child_membership.id))
        self.assertEqual(response.data["user"], self.child_user.id)
        self.assertEqual(response.data["access_state"], "managed")
        self.assertNotIn("birth_date", response.data)
        self.assertNotIn("growth", response.data)

    def test_family_member_without_guardian_authority_is_forbidden(self):
        response = self.get_identity(self.other)
        self.assertEqual(response.status_code, 403)

    def test_cross_family_lookup_is_not_found(self):
        response = self.get_identity(self.outsider)
        self.assertEqual(response.status_code, 404)
