from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from entitlements.catalog import COMMERCIAL_CUTOVER_KEY
from entitlements.models import CapabilityDefinition, EntitlementCutover, EntitlementGrant
from entitlements.services import resolve_entitlements, resolve_entitlements_for_families
from mailing.models import TransactionalEmail

from .models import Family, FamilyInvitation, Membership


class SuperadminFamilyQueryBudgetTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(username="family-query-admin", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        now = timezone.now()
        CapabilityDefinition.objects.create(
            key="core_light",
            domain="core",
            description="Core light capability",
            default_light=True,
            premium=False,
        )
        CapabilityDefinition.objects.create(
            key="premium_feature",
            domain="core",
            description="Premium capability",
            default_light=False,
            premium=True,
        )
        EntitlementCutover.objects.create(
            key=COMMERCIAL_CUTOVER_KEY,
            cutover_at=now - timedelta(days=1),
            applied_at=now,
            eligible_family_count=0,
        )

    def _family_with_pending_sent_invite(self, index):
        now = timezone.now()
        family = Family.objects.create(name=f"Query Family {index}", slug=f"query-family-{index}")
        invite = FamilyInvitation.objects.create(
            family=family,
            role=Membership.Role.OWNER,
            email=f"owner-{index}@example.test",
            display_name=f"Owner {index}",
            expires_at=now + timedelta(days=3),
            token=f"query-budget-token-{index}",
        )
        TransactionalEmail.objects.create(
            message_key=f"query-budget-invite-{index}",
            template_key="family.invitation",
            recipient=invite.email,
            recipient_hash=f"{index:064d}",
            reference_type="family.invitation",
            reference_id=f"{invite.pk}:nonce-{index}",
            status=TransactionalEmail.Status.SENT,
            next_attempt_at=now,
            sent_at=now - timedelta(minutes=index + 1),
        )
        return family

    def test_bulk_entitlement_resolver_matches_single_family_semantics(self):
        family_a = Family.objects.create(name="Entitlement A", slug="entitlement-a")
        family_b = Family.objects.create(name="Entitlement B", slug="entitlement-b")
        EntitlementGrant.objects.create(
            family=family_a,
            origin=EntitlementGrant.Origin.ADMIN_GRANT,
            capability_set=["premium_feature"],
            reason="query budget fixture",
        )

        expected = {
            family_a.pk: resolve_entitlements(family_a).as_dict(),
            family_b.pk: resolve_entitlements(family_b).as_dict(),
        }
        actual = {
            family_id: snapshot.as_dict()
            for family_id, snapshot in resolve_entitlements_for_families([family_a, family_b]).items()
        }

        self.assertEqual(actual, expected)
        self.assertEqual(actual[family_a.pk]["tier"], "premium")
        self.assertEqual(actual[family_b.pk]["tier"], "light")

    def test_family_directory_query_count_does_not_scale_per_family_or_pending_invite(self):
        self._family_with_pending_sent_invite(1)
        with CaptureQueriesContext(connection) as single_queries:
            single_response = self.client.get("/api/superadmin/families/")
        self.assertEqual(single_response.status_code, 200, single_response.data)
        self.assertEqual(single_response.data[0]["pending_owner_invites"][0]["delivery_status"], "sent")

        for index in range(2, 7):
            self._family_with_pending_sent_invite(index)
        with CaptureQueriesContext(connection) as many_queries:
            many_response = self.client.get("/api/superadmin/families/")

        self.assertEqual(many_response.status_code, 200, many_response.data)
        self.assertEqual(len(many_response.data), 6)
        self.assertLessEqual(
            len(many_queries),
            len(single_queries) + 1,
            f"Family directory query count scaled from {len(single_queries)} to {len(many_queries)}",
        )
        for family in many_response.data:
            self.assertEqual(family["pending_owner_invites"][0]["delivery_status"], "sent")
