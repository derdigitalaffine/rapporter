from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family

from .catalog import COMMERCIAL_CUTOVER_KEY
from .models import EntitlementCutover, EntitlementGrant
from .services import (
    ADMIN_TIER_OVERRIDE_MODE,
    clear_admin_tier_override,
    resolve_entitlements,
    set_admin_tier_override,
)


class SuperadminTierOverrideTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superadmin = User.objects.create_superuser(
            username="tier-root",
            password="test-pass-123",
            email="tier-root@example.com",
        )
        self.normal_user = User.objects.create_user(username="tier-user", password="test-pass-123")
        self.family = Family.objects.create(name="Tier Family", slug="tier-family")
        self.now = timezone.now()
        EntitlementCutover.objects.create(
            key=COMMERCIAL_CUTOVER_KEY,
            cutover_at=self.now,
            applied_at=self.now,
            eligible_family_count=0,
        )

    def _subscription(self, plan="premium"):
        return EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.SUBSCRIPTION,
            plan_key=plan,
            active=True,
            starts_at=self.now - timedelta(days=1),
        )

    def test_light_override_supersedes_billing_without_mutating_subscription(self):
        subscription = self._subscription("premium")
        self.assertEqual(resolve_entitlements(self.family).tier, "premium")

        override = set_admin_tier_override(
            actor=self.superadmin,
            family=self.family,
            tier="light",
            reason="Support downgrade",
        )
        snapshot = resolve_entitlements(self.family)
        self.assertEqual(snapshot.tier, "light")
        self.assertEqual(snapshot.override_tier, "light")
        self.assertEqual(override.metadata["mode"], ADMIN_TIER_OVERRIDE_MODE)

        subscription.refresh_from_db()
        self.assertTrue(subscription.active)
        self.assertIsNone(subscription.revoked_at)

        clear_admin_tier_override(
            actor=self.superadmin,
            family=self.family,
            reason="Support override beendet",
        )
        self.assertEqual(resolve_entitlements(self.family).tier, "premium")
        subscription.refresh_from_db()
        self.assertTrue(subscription.active)

    def test_expired_override_automatically_falls_back_to_underlying_vip(self):
        EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.PURCHASED_LIFETIME,
            plan_key="vip",
            active=True,
            starts_at=self.now - timedelta(days=10),
        )
        override = EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.ADMIN_GRANT,
            plan_key="premium",
            active=True,
            starts_at=self.now - timedelta(hours=1),
            ends_at=self.now + timedelta(hours=1),
            metadata={"mode": ADMIN_TIER_OVERRIDE_MODE},
            created_by=self.superadmin,
            reason="Temporary support tier",
        )

        during = resolve_entitlements(self.family, at=self.now)
        after = resolve_entitlements(self.family, at=override.ends_at + timedelta(seconds=1))
        self.assertEqual(during.tier, "premium")
        self.assertEqual(after.tier, "vip")
        self.assertIsNone(after.override_tier)

    def test_replacing_override_revokes_old_override_but_not_other_admin_grants(self):
        feature_grant = EntitlementGrant.objects.create(
            family=self.family,
            origin=EntitlementGrant.Origin.ADMIN_GRANT,
            capability_set=["travel"],
            active=True,
            created_by=self.superadmin,
            reason="Feature support",
            metadata={"ticket": "support-1"},
        )
        old = set_admin_tier_override(
            actor=self.superadmin,
            family=self.family,
            tier="premium",
            reason="First override",
        )
        new = set_admin_tier_override(
            actor=self.superadmin,
            family=self.family,
            tier="vip",
            reason="Replacement override",
        )

        old.refresh_from_db()
        feature_grant.refresh_from_db()
        self.assertFalse(old.active)
        self.assertIsNotNone(old.revoked_at)
        self.assertTrue(feature_grant.active)
        self.assertTrue(new.active)
        self.assertEqual(resolve_entitlements(self.family).tier, "vip")

    def test_superadmin_api_sets_and_clears_override_and_normal_user_is_denied(self):
        self._subscription("premium")
        url = f"/api/superadmin/families/{self.family.id}/entitlement-override/"

        denied = APIClient()
        denied.force_authenticate(self.normal_user)
        self.assertEqual(
            denied.put(url, {"tier": "light", "reason": "not allowed"}, format="json").status_code,
            403,
        )

        client = APIClient()
        client.force_authenticate(self.superadmin)
        ends_at = timezone.now() + timedelta(days=2)
        response = client.put(
            url,
            {"tier": "light", "reason": "Temporary commercial exception", "ends_at": ends_at.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["effective"]["tier"], "light")
        self.assertEqual(response.data["override"]["tier"], "light")
        self.assertEqual(response.data["fallback"], "automatic")
        self.assertEqual(response.data["data_retention"], "non_destructive")
        self.assertFalse(response.data["security"]["fresh_reauth_required"])
        self.assertTrue(response.data["security"]["fresh_reauth_planned"])

        detail = client.get(f"/api/superadmin/families/{self.family.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["entitlement_control"]["effective"]["tier"], "light")

        cleared = client.delete(url, {"reason": "Exception beendet"}, format="json")
        self.assertEqual(cleared.status_code, 200)
        self.assertIsNone(cleared.data["override"])
        self.assertEqual(cleared.data["effective"]["tier"], "premium")

    def test_api_rejects_missing_reason_and_unknown_tier(self):
        client = APIClient()
        client.force_authenticate(self.superadmin)
        url = f"/api/superadmin/families/{self.family.id}/entitlement-override/"

        missing_reason = client.put(url, {"tier": "light"}, format="json")
        self.assertEqual(missing_reason.status_code, 400)
        unknown = client.put(url, {"tier": "enterprise", "reason": "future tier not registered yet"}, format="json")
        self.assertEqual(unknown.status_code, 400)
