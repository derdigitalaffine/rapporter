from datetime import timedelta
from importlib import import_module

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family, Membership

from .catalog import LEGACY_SOURCE_REF
from .models import CapabilityDefinition, EntitlementGrant, EntitlementGrantAudit
from .services import create_admin_grant, require_capability, resolve_entitlements, revoke_admin_grant


class EntitlementCoreTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="ent-alice", password="test-pass-123")
        self.bob = User.objects.create_user(username="ent-bob", password="test-pass-123")
        self.superadmin = User.objects.create_superuser(username="ent-root", password="test-pass-123", email="root@example.com")
        self.family = Family.objects.create(name="Entitlement Family", slug="entitlement-family")
        self.other = Family.objects.create(name="Other Entitlement Family", slug="other-entitlement-family")
        Membership.objects.create(family=self.family, user=self.alice, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other, user=self.bob, role=Membership.Role.OWNER)
        self.now = timezone.now()

    def test_new_family_defaults_to_light_capabilities(self):
        snapshot = resolve_entitlements(self.family, at=self.now)
        self.assertEqual(snapshot.tier, "light")
        self.assertEqual(snapshot.origin_summary, "default_light")
        self.assertTrue({"family_management", "calendar", "todo", "shopping", "pinboard", "notes"}.issubset(snapshot.capabilities))
        self.assertNotIn("travel", snapshot.capabilities)
        self.assertNotIn("documents", snapshot.capabilities)

    def test_active_grants_combine_but_future_expired_revoked_and_inactive_do_not(self):
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.PROMOTION,
            capability_set=["travel"],
            active=True,
            ends_at=self.now + timedelta(days=1),
        )
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.SUBSCRIPTION,
            capability_set=["children"],
            active=True,
            starts_at=self.now - timedelta(days=1),
            ends_at=self.now + timedelta(days=1),
        )
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.PROMOTION,
            capability_set=["documents"],
            active=True,
            ends_at=self.now,
        )
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.PROMOTION,
            capability_set=["pets"],
            active=True,
            starts_at=self.now + timedelta(seconds=1),
        )
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.PROMOTION,
            capability_set=["school"],
            active=False,
        )
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.PROMOTION,
            capability_set=["pregnancy_baby"],
            active=False,
            revoked_at=self.now - timedelta(minutes=1),
        )

        snapshot = resolve_entitlements(self.family, at=self.now)
        self.assertEqual(snapshot.tier, "premium")
        self.assertIn("travel", snapshot.capabilities)
        self.assertIn("children", snapshot.capabilities)
        self.assertNotIn("documents", snapshot.capabilities)
        self.assertNotIn("pets", snapshot.capabilities)
        self.assertNotIn("school", snapshot.capabilities)
        self.assertNotIn("pregnancy_baby", snapshot.capabilities)

    def test_vip_plan_grants_all_non_deprecated_capabilities(self):
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.PURCHASED_LIFETIME,
            plan_key="vip",
            active=True,
        )
        snapshot = resolve_entitlements(self.family, at=self.now)
        expected = set(CapabilityDefinition.objects.filter(deprecated=False).values_list("key", flat=True))
        self.assertEqual(snapshot.tier, "vip")
        self.assertEqual(set(snapshot.capabilities), expected)
        self.assertEqual(snapshot.origin_summary, EntitlementGrant.Origin.PURCHASED_LIFETIME)

    def test_source_ref_alone_never_authorizes(self):
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.SUBSCRIPTION,
            source_ref="provider:says-paid",
            plan_key="vip",
            active=False,
        )
        self.assertEqual(resolve_entitlements(self.family, at=self.now).tier, "light")

    def test_feature_gate_checks_membership_before_entitlement(self):
        EntitlementGrant.objects.create(
            family=self.other,
            origin=EntitlementGrant.Origin.PROMOTION,
            capability_set=["travel"],
            active=True,
        )
        self.assertTrue(require_capability(self.alice, self.family, "todo", at=self.now))
        with self.assertRaises(PermissionDenied):
            require_capability(self.alice, self.family, "travel", at=self.now)
        with self.assertRaises(PermissionDenied):
            require_capability(self.alice, self.other, "travel", at=self.now)

    def test_admin_grants_require_superadmin_and_are_audited_on_grant_and_revoke(self):
        with self.assertRaises(PermissionDenied):
            create_admin_grant(
                actor=self.alice,
                family=self.family,
                capability_set=["travel"],
                reason="not allowed",
            )

        grant = create_admin_grant(
            actor=self.superadmin,
            family=self.family,
            capability_set=["travel"],
            reason="Support-Freischaltung",
            metadata={"ticket": "support-42"},
        )
        granted_audit = EntitlementGrantAudit.objects.get(grant=grant, action=EntitlementGrantAudit.Action.GRANTED)
        self.assertEqual(granted_audit.actor, self.superadmin)
        self.assertEqual(granted_audit.reason, "Support-Freischaltung")
        self.assertNotIn("ticket", granted_audit.snapshot)
        self.assertIn("travel", resolve_entitlements(self.family, at=self.now).capabilities)

        revoke_admin_grant(actor=self.superadmin, grant=grant, reason="Support-Freischaltung beendet")
        grant.refresh_from_db()
        self.assertFalse(grant.active)
        self.assertIsNotNone(grant.revoked_at)
        self.assertEqual(EntitlementGrantAudit.objects.filter(grant=grant).count(), 2)
        self.assertNotIn("travel", resolve_entitlements(self.family, at=timezone.now()).capabilities)

    def test_admin_grant_validation_is_bounded_and_fail_closed(self):
        with self.assertRaises(ValidationError):
            create_admin_grant(actor=self.superadmin, family=self.family, plan_key="unknown", reason="invalid")
        with self.assertRaises(ValidationError):
            create_admin_grant(actor=self.superadmin, family=self.family, capability_set=["not-real"], reason="invalid")
        with self.assertRaises(ValidationError):
            create_admin_grant(
                actor=self.superadmin,
                family=self.family,
                capability_set=["travel"],
                reason="too much metadata",
                metadata={"payload": "x" * 5000},
            )

    def test_legacy_backfill_is_idempotent_and_grants_existing_family_full_access(self):
        migration = import_module("entitlements.migrations.0001_initial")
        migration.seed_capabilities_and_legacy(global_apps, None)
        migration.seed_capabilities_and_legacy(global_apps, None)

        grants = EntitlementGrant.objects.filter(
            family=self.family,
            origin=EntitlementGrant.Origin.LEGACY_GRANDFATHERED,
            source_ref=LEGACY_SOURCE_REF,
        )
        self.assertEqual(grants.count(), 1)
        snapshot = resolve_entitlements(self.family, at=timezone.now())
        expected = set(CapabilityDefinition.objects.filter(deprecated=False).values_list("key", flat=True))
        self.assertEqual(snapshot.tier, "vip")
        self.assertEqual(snapshot.origin_summary, EntitlementGrant.Origin.LEGACY_GRANDFATHERED)
        self.assertEqual(set(snapshot.capabilities), expected)

    def test_snapshot_api_is_read_only_and_cross_family_safe(self):
        client = APIClient()
        client.force_authenticate(self.alice)
        own = client.get(f"/api/entitlements/?family={self.family.id}")
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.data["family"], str(self.family.id))
        self.assertEqual(own.data["tier"], "light")
        self.assertIn("todo", own.data["capabilities"])

        foreign = client.get(f"/api/entitlements/?family={self.other.id}")
        self.assertEqual(foreign.status_code, 403)
        self.assertNotIn(self.other.name, str(foreign.data))
        invalid = client.get("/api/entitlements/?family=not-a-uuid")
        self.assertEqual(invalid.status_code, 400)
