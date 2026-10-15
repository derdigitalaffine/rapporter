import uuid
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from auth_sessions.models import AuthSession
from family.family_relationship_models import FamilyRelationship
from family.models import Family, FamilyEvent, Membership

from .development_service import ensure_u_exam_events
from .models import CareCircleAccess, FamilyModuleSetting, ManagedChildGuardian
from .pregnancy_service import create_managed_child


User = get_user_model()
PASSWORD = "custody-test-password-717"


class CustodyAuthorizationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="custody-owner-717", password=PASSWORD)
        self.adult = User.objects.create_user(username="custody-adult-717", password=PASSWORD)
        self.outsider = User.objects.create_user(username="custody-outsider-717", password=PASSWORD)
        self.family = Family.objects.create(name="Custody ACL", slug="custody-acl-717")
        self.other_family = Family.objects.create(name="Custody Other", slug="custody-acl-other-717")
        self.owner_membership = Membership.objects.create(family=self.family,user=self.owner,role=Membership.Role.OWNER,display_name="Alex")
        self.adult_membership = Membership.objects.create(family=self.family,user=self.adult,role=Membership.Role.ADULT,display_name="Kim")
        self.outsider_membership = Membership.objects.create(family=self.other_family,user=self.outsider,role=Membership.Role.OWNER,display_name="Outside")
        self.baby = create_managed_child(
            self.owner,
            self.family,
            display_name="Mia",
            birth_date=date.today() - timedelta(days=45),
            client_identity_key=uuid.uuid4(),
        )
        FamilyModuleSetting.objects.create(
            family=self.family,
            module_key="pregnancy_baby",
            enabled=True,
            enabled_by=self.owner,
            enabled_at=timezone.now(),
        )

    def test_existing_custody_creates_preventive_appointments_without_guardian_or_care_grant(self):
        FamilyRelationship.objects.create(
            family=self.family,
            child_membership=self.baby.membership,
            related_membership=self.owner_membership,
            kind=FamilyRelationship.Kind.PARENT,
            has_custody=True,
            status=FamilyRelationship.Status.ACTIVE,
        )
        self.assertFalse(ManagedChildGuardian.objects.filter(baby=self.baby).exists())
        self.assertFalse(CareCircleAccess.objects.filter(family=self.family,membership=self.owner_membership).exists())

        events = ensure_u_exam_events(self.owner, self.baby.id)

        self.assertTrue(events)
        self.assertTrue(
            FamilyEvent.objects.filter(
                family=self.family,
                type="family.appointment",
                external_id__startswith="familyos-private:",
            ).exists()
        )

    def test_adult_without_custody_or_care_access_cannot_create_preventive_appointments(self):
        with self.assertRaises(PermissionDenied):
            ensure_u_exam_events(self.adult, self.baby.id)

    @override_settings(AUTH_SESSION_FRESH_SECONDS=60)
    def test_custody_write_requires_fresh_reauth_and_then_becomes_effective(self):
        client = APIClient()
        login = client.post(
            "/api/auth/login/",
            {"username": self.owner.username, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)
        AuthSession.objects.filter(user=self.owner, revoked_at__isnull=True).update(
            last_reauthenticated_at=timezone.now() - timedelta(minutes=10)
        )
        payload = {
            "family": str(self.family.id),
            "child_membership": str(self.baby.membership_id),
            "related_membership": str(self.owner_membership.id),
            "kind": "parent",
            "has_custody": True,
            "status": "active",
        }
        blocked = client.post("/api/family-relationships/", payload, format="json")
        self.assertEqual(blocked.status_code, 403, blocked.data)
        self.assertEqual(blocked.data["code"], "reauth_required")
        self.assertFalse(FamilyRelationship.objects.filter(child_membership=self.baby.membership,has_custody=True).exists())

        reauth = client.post("/api/auth/reauth/password/", {"password": PASSWORD}, format="json")
        self.assertEqual(reauth.status_code, 200, reauth.data)
        created = client.post("/api/family-relationships/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertTrue(created.data["permission_suggestions"]["child_authority"])

        events = ensure_u_exam_events(self.owner, self.baby.id)
        self.assertTrue(events)

    def test_cross_family_related_member_is_rejected(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.post(
            "/api/family-relationships/",
            {
                "family": str(self.family.id),
                "child_membership": str(self.baby.membership_id),
                "related_membership": str(self.outsider_membership.id),
                "kind": "parent",
                "has_custody": False,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(FamilyRelationship.objects.filter(related_membership=self.outsider_membership).exists())