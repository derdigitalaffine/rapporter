import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.family_relationship_models import FamilyRelationship
from family.models import Family, Membership, FamilyEvent
from .models import BabyProfile, CareCircleAccess, ChildHealthRecord, FamilyModuleSetting
from .pregnancy_service import create_managed_child
from .family_modules import set_module
from .reference_service import create_reference_draft, publish_reference_package, DEFAULT_SOURCE_KEY


class ChildrenHubTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.parent = User.objects.create_user(username="hub-parent", password="children-test-password")
        self.helper = User.objects.create_user(username="hub-helper")
        self.family = Family.objects.create(name="Children Hub", slug="children-hub")
        self.parent_member = Membership.objects.create(user=self.parent, family=self.family, role="adult")
        self.helper_member = Membership.objects.create(user=self.helper, family=self.family, role="adult")
        FamilyModuleSetting.objects.create(family=self.family, module_key="pregnancy_baby", enabled=True)
        self.child = create_managed_child(self.parent, self.family, display_name="Mia", birth_date=timezone.localdate() - timedelta(days=365*5), client_identity_key=uuid.uuid4())
        self.other = create_managed_child(self.parent, self.family, display_name="Ben", birth_date=timezone.localdate() - timedelta(days=40), client_identity_key=uuid.uuid4())
        self.custody = FamilyRelationship.objects.create(family=self.family, child_membership=self.child.membership,
            related_membership=self.parent_member, kind="parent", has_custody=True, status="active")
        self.client = APIClient()
        self.client.force_authenticate(self.parent)

    def test_custody_discovers_only_own_child_without_global_care_grant(self):
        module = self.client.get(f"/api/baby/module/?family={self.family.id}")
        self.assertTrue(module.data["authorized"])
        self.assertFalse(module.data["permissions"]["can_view_pregnancy"])
        profiles = self.client.get(f"/api/baby/profiles/?family={self.family.id}")
        self.assertEqual([row["id"] for row in profiles.data["babies"]], [str(self.child.id)])
        self.assertTrue(profiles.data["babies"][0]["permissions"]["can_manage_care_circle"])
        self.assertEqual(self.client.get(f"/api/baby/profiles/{self.other.id}/health/").status_code, 403)

    def test_custody_cannot_be_downgraded_by_empty_care_grant_and_revoke_is_immediate(self):
        CareCircleAccess.objects.create(family=self.family, baby=self.child, membership=self.parent_member)
        self.assertEqual(self.client.get(f"/api/baby/profiles/{self.child.id}/health/").status_code, 200)
        self.custody.has_custody = False
        self.custody.save()
        self.assertEqual(self.client.get(f"/api/baby/profiles/{self.child.id}/health/").status_code, 403)

    def test_delegation_is_child_scoped_and_never_account_authority(self):
        CareCircleAccess.objects.create(family=self.family, baby=self.child, membership=self.helper_member, can_view_growth_development=True)
        self.client.force_authenticate(self.helper)
        self.assertEqual(self.client.get(f"/api/baby/profiles/{self.child.id}/health/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/baby/profiles/{self.other.id}/health/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/baby/profiles/{self.child.id}/care-circle/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/baby/profiles/{self.child.id}/identity/").status_code, 403)

    def test_care_circle_mutation_requires_fresh_session(self):
        response = self.client.put(f"/api/baby/profiles/{self.child.id}/care-circle/", {"care_circle": []}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "reauth_required")
        self.client.force_authenticate(None)
        login = self.client.post("/api/auth/login/", {"username": "hub-parent", "password": "children-test-password"}, format="json")
        self.assertEqual(login.status_code, 200)
        granted = self.client.put(f"/api/baby/profiles/{self.child.id}/care-circle/", {"care_circle": [
            {"membership": str(self.helper_member.id), "can_log_care": True}
        ]}, format="json")
        self.assertEqual(granted.status_code, 200, granted.data)
        self.assertFalse(CareCircleAccess.objects.get(baby=self.child).is_guardian)

    def test_historical_unknown_is_read_only_until_explicit_backfill_and_no_events(self):
        response = self.client.get(f"/api/baby/profiles/{self.child.id}/health/")
        past = [row for row in response.data["items"] if row["historical"]]
        self.assertTrue(past)
        self.assertTrue(all(row["state"] == "unknown" for row in past))
        self.assertFalse(ChildHealthRecord.objects.exists())
        self.assertFalse(FamilyEvent.objects.exists())
        saved = self.client.post(f"/api/baby/profiles/{self.child.id}/health/", {"entries": [
            {"key": row["key"], "state": "done", "expected_version": 0} for row in past
        ]}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertFalse(FamilyEvent.objects.exists())

    def test_version_conflict_retry_and_invalid_bulk_are_atomic(self):
        path = f"/api/baby/profiles/{self.child.id}/health/"
        value = {"key": "exam:U2", "state": "done", "expected_version": 0}
        self.assertEqual(self.client.post(path, value, format="json").status_code, 200)
        self.assertEqual(self.client.post(path, value, format="json").status_code, 200)
        self.assertEqual(ChildHealthRecord.objects.count(), 1)
        self.assertEqual(self.client.post(path, {**value, "state": "later"}, format="json").status_code, 409)
        invalid = self.client.post(path, {"entries": [
            {"key": "exam:U3", "state": "done", "expected_version": 0},
            {"key": "exam:unknown", "state": "done", "expected_version": 0}
        ]}, format="json")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(ChildHealthRecord.objects.count(), 1)

    def test_plan_is_explicit_generic_calendar_and_not_an_old_window_alarm(self):
        path = f"/api/baby/profiles/{self.child.id}/health/"
        value = {"key": "exam:U9", "state": "planned", "expected_version": 0,
                 "planned_at": (timezone.now() + timedelta(days=2)).isoformat()}
        response = self.client.post(path, value, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        event = FamilyEvent.objects.get()
        self.assertNotIn(str(self.child.id), str(event.payload))
        self.assertNotIn(self.child.display_name, str(event.payload))
        self.assertNotIn("U9", event.title)
        resolved = self.client.get(f"/api/baby/health-events/{event.id}/")
        self.assertEqual(resolved.data["baby"], str(self.child.id))
        self.client.force_authenticate(self.helper)
        self.assertEqual(self.client.get(f"/api/baby/health-events/{event.id}/").status_code, 403)

    def test_manual_vaccination_is_documentation_not_an_invented_recommendation(self):
        path = f"/api/baby/profiles/{self.child.id}/health/"
        self.assertFalse(self.client.get(path).data["vaccination_reference_available"])
        response = self.client.post(path, {"key": f"manual:{uuid.uuid4()}", "title": "Documented vaccination",
            "state": "done", "expected_version": 0, "occurred_on": timezone.localdate().isoformat(), "batch": "documented-batch"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ChildHealthRecord.objects.get().reference, {})

    def test_cross_family_and_plain_owner_do_not_gain_child_access(self):
        other_family = Family.objects.create(name="Outside", slug="hub-outside")
        owner = get_user_model().objects.create_user(username="outside-owner")
        Membership.objects.create(user=owner, family=other_family, role="owner")
        self.client.force_authenticate(owner)
        self.assertIn(self.client.get(f"/api/baby/profiles/{self.child.id}/health/").status_code, [403, 404])
        self.client.force_authenticate(self.helper)
        self.assertFalse(self.client.get(f"/api/baby/module/?family={self.family.id}").data["authorized"])

    def test_module_activation_does_not_create_guardian_or_child_access(self):
        set_module(self.helper, self.family, enabled=True)
        self.client.force_authenticate(self.helper)
        profiles = self.client.get(f"/api/baby/profiles/?family={self.family.id}")
        self.assertEqual(profiles.data["babies"], [])
        self.assertFalse(CareCircleAccess.objects.get(membership=self.helper_member,baby__isnull=True).is_guardian)
        self.assertEqual(self.client.get(f"/api/baby/profiles/{self.child.id}/health/").status_code, 403)

    def test_new_guardian_or_pregnancy_grant_cannot_be_smuggled_into_child_circle(self):
        from .family_modules import set_care_circle
        from rest_framework.exceptions import ValidationError
        for fields in [{"is_guardian": True}, {"can_view_pregnancy": True}]:
            with self.assertRaises(ValidationError):
                set_care_circle(self.parent,self.family,[{"membership":self.helper_member.id,**fields}],baby=self.child)
        self.assertFalse(CareCircleAccess.objects.filter(baby=self.child).exists())

    def test_discovery_query_count_is_constant_across_children(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from .child_identity_service import child_access_overview
        with CaptureQueriesContext(connection) as small:
            child_access_overview(self.parent,self.family)
        for index in range(4):
            child = create_managed_child(self.parent,self.family,display_name=f"Child {index}",birth_date=timezone.localdate(),client_identity_key=uuid.uuid4())
            FamilyRelationship.objects.create(family=self.family,child_membership=child.membership,related_membership=self.parent_member,kind="parent",has_custody=True,status="active")
        with CaptureQueriesContext(connection) as large:
            child_access_overview(self.parent,self.family)
        self.assertEqual(len(small),len(large))

    def test_only_published_vaccination_references_are_projected_and_provenance_is_kept(self):
        from .test_reference_data import reference_payload
        admin = get_user_model().objects.create_superuser(username="hub-reference-admin",email="reference@example.invalid")
        package = create_reference_draft(admin,source_key=DEFAULT_SOURCE_KEY,source_title="Synthetic reference",source_version="fixture-1",locale="de-DE",payload=reference_payload())
        path = f"/api/baby/profiles/{self.child.id}/health/"
        self.assertFalse(self.client.get(path).data["vaccination_reference_available"])
        publish_reference_package(admin,package.id)
        response = self.client.get(path)
        vaccines = [row for row in response.data["items"] if row["kind"] == "vaccination"]
        self.assertEqual(len(vaccines),3)
        saved = self.client.post(path,{"key":vaccines[0]["key"],"state":"done","expected_version":0,"reference_checksum":package.checksum},format="json")
        self.assertEqual(saved.status_code,200,saved.data)
        record = ChildHealthRecord.objects.get()
        self.assertEqual(record.reference["package_id"],str(package.id))
        self.assertEqual(record.reference["checksum"],package.checksum)
        self.assertFalse(FamilyEvent.objects.exists())

    def test_explicit_custody_during_create_is_atomic_fresh_owner_only_and_retry_safe(self):
        self.parent_member.role = "owner"
        self.parent_member.save()
        payload = {"family":str(self.family.id),"display_name":"New child","birth_date":"2020-01-01","client_identity_key":str(uuid.uuid4()),"custody_for_self":True}
        before = self.family.baby_profiles.count()
        self.assertEqual(self.client.post("/api/baby/managed-children/",payload,format="json").status_code,403)
        self.assertEqual(self.family.baby_profiles.count(),before)
        self.client.force_authenticate(None)
        self.client.post("/api/auth/login/",{"username":"hub-parent","password":"children-test-password"},format="json")
        first = self.client.post("/api/baby/managed-children/",payload,format="json")
        self.assertEqual(first.status_code,201,first.data)
        second = self.client.post("/api/baby/managed-children/",payload,format="json")
        self.assertEqual(second.data["baby"],first.data["baby"])
        relation = FamilyRelationship.objects.get(child_membership_id=first.data["membership"],related_membership=self.parent_member)
        self.assertTrue(relation.has_custody)
        relation.has_custody = False
        relation.save()
        self.client.post("/api/baby/managed-children/",payload,format="json")
        relation.refresh_from_db()
        self.assertFalse(relation.has_custody)

    def test_cross_family_identity_retry_never_returns_foreign_child(self):
        other_family = Family.objects.create(name="Retry Other",slug="retry-other-hub")
        Membership.objects.create(user=self.parent,family=other_family,role="owner")
        key = self.child.client_identity_key
        response = self.client.post("/api/baby/managed-children/",{"family":str(other_family.id),"display_name":"Do not leak","birth_date":"2020-01-01","client_identity_key":str(key)},format="json")
        self.assertEqual(response.status_code,400)
        self.assertFalse(other_family.baby_profiles.exists())

    def test_reverse_migration_refuses_to_drop_scoped_grants_or_health_history(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        migration = import_module("baby.migrations.0005_childhealthrecord_and_more")
        with connection.schema_editor(atomic=False) as editor:
            migration.guard_reverse(apps,editor)
            CareCircleAccess.objects.create(family=self.family,baby=self.child,membership=self.helper_member,can_log_care=True)
            with self.assertRaises(RuntimeError):
                migration.guard_reverse(apps,editor)

    def test_custody_bootstrap_does_not_bypass_owner_only_relationship_authority(self):
        self.client.force_authenticate(None)
        self.client.post("/api/auth/login/",{"username":"hub-parent","password":"children-test-password"},format="json")
        response = self.client.post("/api/baby/managed-children/",{"family":str(self.family.id),"display_name":"New child","birth_date":"2020-01-01","client_identity_key":str(uuid.uuid4()),"custody_for_self":True},format="json")
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.family.baby_profiles.count(),2)

    def test_existing_child_is_attached_without_recreating_user_or_resetting_login(self):
        User = get_user_model()
        user = User.objects.create_user(username="existing-child",password="existing-child-password",email="child@example.invalid")
        child = Membership.objects.create(family=self.family,user=user,role="child",display_name="Existing child")
        FamilyRelationship.objects.create(family=self.family,child_membership=child,related_membership=self.parent_member,kind="parent",has_custody=True,status="active")
        before = User.objects.count()
        password = user.password
        response = self.client.post("/api/baby/managed-children/",{"family":str(self.family.id),"membership":str(child.id),"display_name":"Existing child","birth_date":"2018-01-01","client_identity_key":str(uuid.uuid4())},format="json")
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data["membership"],str(child.id))
        self.assertEqual(User.objects.count(),before)
        user.refresh_from_db()
        self.assertEqual(user.password,password)
        self.assertEqual(user.email,"child@example.invalid")

    def test_attach_preserves_partial_birthday_and_rejects_an_existing_creation_key(self):
        from family.models import UserProfile
        user = get_user_model().objects.create_user(username="partial-birthday")
        child = Membership.objects.create(family=self.family,user=user,role="child",display_name="Existing child")
        FamilyRelationship.objects.create(family=self.family,child_membership=child,related_membership=self.parent_member,kind="parent",has_custody=True,status="active")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.birth_year = 2018
        profile.save()
        values = {"family":str(self.family.id),"membership":str(child.id),"display_name":"Existing child","birth_date":"2019-01-01","client_identity_key":str(uuid.uuid4())}
        path = "/api/baby/managed-children/"
        self.assertEqual(self.client.post(path,values,format="json").status_code,400)
        profile.refresh_from_db()
        self.assertEqual(profile.birth_year,2018)
        self.assertFalse(BabyProfile.objects.filter(membership=child).exists())
        values.update(birth_date="2018-01-01",client_identity_key=str(self.child.client_identity_key))
        self.assertEqual(self.client.post(path,values,format="json").status_code,400)
        self.assertFalse(BabyProfile.objects.filter(membership=child).exists())
