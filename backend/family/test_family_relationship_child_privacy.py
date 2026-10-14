from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .family_relationship_models import FamilyRelationship
from .models import Family, Membership


User = get_user_model()


class FamilyRelationshipChildPrivacyTests(TestCase):
    def test_child_can_only_read_relationships_for_own_profile(self):
        family = Family.objects.create(name="Patchwork Privacy", slug="patchwork-privacy")
        owner = User.objects.create_user(username="privacy-owner", password="test-password")
        child_a = User.objects.create_user(username="privacy-child-a", password="test-password")
        child_b = User.objects.create_user(username="privacy-child-b", password="test-password")
        owner_membership = Membership.objects.create(
            family=family,
            user=owner,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        child_a_membership = Membership.objects.create(
            family=family,
            user=child_a,
            role=Membership.Role.CHILD,
            display_name="Mia",
        )
        child_b_membership = Membership.objects.create(
            family=family,
            user=child_b,
            role=Membership.Role.CHILD,
            display_name="Noah",
        )
        FamilyRelationship.objects.create(
            family=family,
            child_membership=child_a_membership,
            related_membership=owner_membership,
            kind=FamilyRelationship.Kind.PARENT,
            child_visibility=FamilyRelationship.ChildVisibility.RELATIONSHIP_ONLY,
        )
        FamilyRelationship.objects.create(
            family=family,
            child_membership=child_b_membership,
            related_membership=owner_membership,
            kind=FamilyRelationship.Kind.PARENT,
            child_visibility=FamilyRelationship.ChildVisibility.FULL,
            is_biological_parent=True,
            is_legal_parent=True,
            has_custody=True,
        )

        client = APIClient()
        client.force_authenticate(user=child_a)
        response = client.get(
            f"/api/family-relationships/?family={family.id}&child_membership={child_b_membership.id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["child_membership"], str(child_a_membership.id))
        self.assertIsNone(response.data[0]["is_biological_parent"])
        self.assertIsNone(response.data[0]["is_legal_parent"])
        self.assertIsNone(response.data[0]["has_custody"])
