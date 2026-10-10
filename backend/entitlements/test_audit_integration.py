from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from family.models import Family
from telemetry.models import AuditEvent

from .models import EntitlementGrant
from .services import apply_commercial_cutover, create_admin_grant, revoke_admin_grant


class EntitlementAuditIntegrationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superadmin = User.objects.create_superuser(
            username="ent-audit-root",
            password="test-pass-123",
            email="ent-audit-root@example.com",
        )
        self.family = Family.objects.create(name="Entitlement Audit Family", slug="entitlement-audit-family")

    def test_admin_grant_and_revoke_are_written_to_global_audit_stream(self):
        grant = create_admin_grant(
            actor=self.superadmin,
            family=self.family,
            plan_key="vip",
            reason="Support-Freischaltung",
        )

        granted = AuditEvent.objects.get(event_key="entitlement.granted", target_id=str(grant.pk))
        self.assertEqual(granted.actor, self.superadmin)
        self.assertEqual(granted.actor_class, AuditEvent.ActorClass.SUPERADMIN)
        self.assertEqual(granted.family, self.family)
        self.assertEqual(granted.target_type, "entitlement")
        self.assertEqual(granted.outcome, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(granted.reason, "admin_action")
        self.assertEqual(granted.metadata, {"origin": EntitlementGrant.Origin.ADMIN_GRANT})

        revoke_admin_grant(
            actor=self.superadmin,
            grant=grant,
            reason="Support-Freischaltung beendet",
        )

        revoked = AuditEvent.objects.get(event_key="entitlement.revoked", target_id=str(grant.pk))
        self.assertEqual(revoked.actor, self.superadmin)
        self.assertEqual(revoked.actor_class, AuditEvent.ActorClass.SUPERADMIN)
        self.assertEqual(revoked.family, self.family)
        self.assertEqual(revoked.target_type, "entitlement")
        self.assertEqual(revoked.outcome, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(revoked.reason, "admin_action")
        self.assertEqual(revoked.metadata, {"origin": EntitlementGrant.Origin.ADMIN_GRANT})

    def test_commercial_cutover_emits_one_system_audit_event_per_created_grant(self):
        cutover_at = timezone.now()

        _marker, created_count = apply_commercial_cutover(cutover_at=cutover_at)
        self.assertEqual(created_count, 1)

        grant = EntitlementGrant.objects.get(
            family=self.family,
            origin=EntitlementGrant.Origin.LEGACY_GRANDFATHERED,
        )
        event = AuditEvent.objects.get(event_key="entitlement.granted", target_id=str(grant.pk))
        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_class, AuditEvent.ActorClass.SYSTEM)
        self.assertEqual(event.family, self.family)
        self.assertEqual(event.target_type, "entitlement")
        self.assertEqual(event.outcome, AuditEvent.Outcome.SUCCESS)
        self.assertEqual(event.reason, "system")
        self.assertEqual(event.metadata, {"origin": EntitlementGrant.Origin.LEGACY_GRANDFATHERED})

        _marker, created_again = apply_commercial_cutover(cutover_at=cutover_at)
        self.assertEqual(created_again, 0)
        self.assertEqual(
            AuditEvent.objects.filter(event_key="entitlement.granted", target_id=str(grant.pk)).count(),
            1,
        )
