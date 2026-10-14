from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .family_relationship_models import FamilyRelationship
from .models import Family, Membership


User = get_user_model()


class FamilyRelationshipTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="relationship-owner",
            password="test-password",
        )
        self.adult = User.objects.create_user(
            username="relationship-adult",
            password="test-password",
        )
        self.child = User.objects.create_user(
            username="relationship-child",
            password="test-password",
        )
        self.other = User.objects.create_user(
            username="relationship-other",
            password="test-password",
        )
        self.family = Family.objects.create(name="Patchwork", slug="patchwork")
        self.other_family = Family.objects.create(
            name="Other",
            slug="patchwork-other",
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
        self.child_membership = Membership.objects.create(
            family=self.family,
            user=self.child,
            role=Membership.Role.CHILD,
            display_name="Mia",
        )
        self.other_membership = Membership.objects.create(
            family=self.other_family,
            user=self.other,
            role=Membership.Role.OWNER,
            display_name="Robin",
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def create_relationship(self, **overrides):
        payload = {
            "family": str(self.family.id),
            "child_membership": str(self.child_membership.id),
            "related_membership": str(self.adult_membership.id),
            "kind": "bonus_parent",
            "custom_label": "Bonus-Papa",
            "is_biological_parent": False,
            "is_legal_parent": True,
            "has_custody": None,
            "child_visibility": "relationship_only",
        }
        payload.update(overrides)
        return self.client_for(self.owner).post(
            "/api/family-relationships/",
            payload,
            format="json",
        )

    def test_owner_can_create_and_deactivate_patchwork_relationship(self):
        response = self.create_relationship()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["label"], "Bonus-Papa")
        self.assertFalse(response.data["permission_suggestions"]["automatic"])
        relationship = FamilyRelationship.objects.get(pk=response.data["id"])
        self.assertFalse(relationship.is_biological_parent)
        self.assertTrue(relationship.is_legal_parent)
        self.assertIsNone(relationship.has_custody)

        patched = self.client_for(self.owner).patch(
            f"/api/family-relationships/{relationship.id}/",
            {"status": "inactive", "has_custody": True},
            format="json",
        )
        self.assertEqual(patched.status_code, 200)
        relationship.refresh_from_db()
        self.assertEqual(relationship.status, FamilyRelationship.Status.INACTIVE)
        self.assertTrue(relationship.has_custody)

    def test_adult_family_role_does_not_allow_relationship_changes(self):
        response = self.client_for(self.adult).post(
            "/api/family-relationships/",
            {
                "family": str(self.family.id),
                "child_membership": str(self.child_membership.id),
                "related_membership": str(self.owner_membership.id),
                "kind": "parent",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(FamilyRelationship.objects.exists())

    def test_adult_family_role_does_not_reveal_sensitive_parent_facts(self):
        created = self.create_relationship(
            is_biological_parent=True,
            is_legal_parent=True,
            has_custody=True,
        )
        self.assertEqual(created.status_code, 201)

        rows = self.client_for(self.adult).get(
            f"/api/family-relationships/?family={self.family.id}"
        )
        self.assertEqual(rows.status_code, 200)
        self.assertEqual(len(rows.data), 1)
        self.assertEqual(rows.data[0]["label"], "Bonus-Papa")
        self.assertIsNone(rows.data[0]["is_biological_parent"])
        self.assertIsNone(rows.data[0]["is_legal_parent"])
        self.assertIsNone(rows.data[0]["has_custody"])
        self.assertIsNone(rows.data[0]["permission_suggestions"])
        self.assertFalse(rows.data[0]["can_edit"])

    def test_cross_family_related_member_is_rejected(self):
        response = self.create_relationship(
            related_membership=str(self.other_membership.id)
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FamilyRelationship.objects.exists())

    def test_free_label_requires_other_and_none_stays_unlabelled(self):
        missing = self.create_relationship(kind="other", custom_label="")
        self.assertEqual(missing.status_code, 400)

        none = self.create_relationship(kind="none", custom_label="")
        self.assertEqual(none.status_code, 201)
        self.assertEqual(none.data["kind"], "none")
        self.assertEqual(none.data["custom_label"], "")
        self.assertEqual(none.data["label"], "")

    def test_child_visibility_redacts_sensitive_parent_facts(self):
        created = self.create_relationship(
            is_biological_parent=True,
            is_legal_parent=True,
            has_custody=True,
        )
        relationship = FamilyRelationship.objects.get(pk=created.data["id"])
        child_client = self.client_for(self.child)

        rows = child_client.get(
            f"/api/family-relationships/?family={self.family.id}"
        )
        self.assertEqual(rows.status_code, 200)
        self.assertEqual(len(rows.data), 1)
        self.assertIsNone(rows.data[0]["is_biological_parent"])
        self.assertIsNone(rows.data[0]["is_legal_parent"])
        self.assertIsNone(rows.data[0]["has_custody"])
        self.assertIsNone(rows.data[0]["permission_suggestions"])
        self.assertEqual(rows.data[0]["label"], "Bonus-Papa")

        relationship.child_visibility = FamilyRelationship.ChildVisibility.HIDDEN
        relationship.save(update_fields=["child_visibility", "updated_at"])
        hidden = child_client.get(
            f"/api/family-relationships/?family={self.family.id}"
        )
        self.assertEqual(hidden.status_code, 200)
        self.assertEqual(hidden.data, [])

    def test_relationship_does_not_change_family_roles(self):
        response = self.create_relationship(
            kind="father",
            is_biological_parent=True,
            is_legal_parent=True,
            has_custody=True,
        )
        self.assertEqual(response.status_code, 201)
        self.adult_membership.refresh_from_db()
        self.child_membership.refresh_from_db()
        self.assertEqual(self.adult_membership.role, Membership.Role.ADULT)
        self.assertEqual(self.child_membership.role, Membership.Role.CHILD)
