from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.family_relationship_models import FamilyRelationship
from family.models import Family, Membership

from .models import BabyProfile, CareCircleAccess, ManagedChildGuardian


User = get_user_model()


class ManagedChildRelationshipDefaultTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="managed-child-owner",
            password="test-password",
        )
        self.adult = User.objects.create_user(
            username="managed-child-adult",
            password="test-password",
        )
        self.family = Family.objects.create(
            name="Patchwork Defaults",
            slug="patchwork-defaults",
        )
        self.owner_membership = Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.adult_membership = Membership.objects.create(
            family=self.family,
            user=self.adult,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_child_creation_grants_account_management_but_infers_no_relationship(self):
        response = self.client.post(
            "/api/baby/managed-children/",
            {
                "family": str(self.family.id),
                "display_name": "Mia",
                "birth_date": "2021-05-06",
                "client_identity_key": str(uuid4()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        baby = BabyProfile.objects.get(pk=response.data["baby"])

        self.assertFalse(
            FamilyRelationship.objects.filter(
                child_membership=baby.membership,
            ).exists()
        )
        self.assertTrue(
            ManagedChildGuardian.objects.filter(
                baby=baby,
                membership=self.owner_membership,
                can_manage_account=True,
            ).exists()
        )
        self.assertFalse(
            ManagedChildGuardian.objects.filter(
                baby=baby,
                membership=self.adult_membership,
            ).exists()
        )
        self.assertFalse(
            CareCircleAccess.objects.filter(
                family=self.family,
                membership=self.owner_membership,
            ).exists()
        )
