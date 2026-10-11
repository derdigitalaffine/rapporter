from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .create_action_models import CreateActionPreference, CreateActionStat, CreateActionUsageReceipt
from .models import Family, Membership


class CreateActionPreferenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice-create-ranking", password="test-pass-123")
        self.bob = User.objects.create_user(username="bob-create-ranking", password="test-pass-123")
        self.family = Family.objects.create(name="Create Ranking", slug="create-ranking", timezone="Europe/Berlin")
        self.other = Family.objects.create(name="Other Ranking", slug="other-create-ranking", timezone="Europe/Berlin")
        self.membership = Membership.objects.create(family=self.family, user=self.alice, role=Membership.Role.OWNER)
        self.other_membership = Membership.objects.create(family=self.other, user=self.bob, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def url(self, family=None):
        return f"/api/create-actions/?family={(family or self.family).id}"

    def usage(self, action_id="task", *, family=None, event_id=None, **extra):
        payload = {
            "event_id": str(event_id or uuid4()),
            "action_id": action_id,
            "origin_page": "tasks",
            "context_bucket": "tasks",
            "success": True,
        }
        payload.update(extra)
        return self.client.post(self.url(family), payload, format="json")

    def test_defaults_are_family_scoped_and_content_free(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["ranking_version"], 1)
        self.assertEqual(response.data["cold_start_threshold"], 5)
        self.assertEqual(response.data["stats"], [])
        self.assertEqual(
            response.data["preferences"],
            {
                "smart_ranking_enabled": True,
                "context_ranking_enabled": True,
                "time_patterns_enabled": False,
                "direct_mode": False,
                "direct_action_id": "",
                "max_quick_actions": 4,
                "pinned_action_ids": [],
                "hidden_action_ids": [],
                "manual_order": [],
                "learning_scope": "family",
            },
        )
        self.assertTrue(CreateActionPreference.objects.filter(membership=self.membership).exists())

    def test_preferences_validate_final_pin_hide_state_and_limits(self):
        response = self.client.patch(
            self.url(),
            {"pinned_action_ids": ["task"], "max_quick_actions": 6, "direct_mode": True, "direct_action_id": "task"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["preferences"]["pinned_action_ids"], ["task"])

        response = self.client.patch(self.url(), {"hidden_action_ids": ["task"]}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(self.url(), {"max_quick_actions": 7}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(self.url(), {"pinned_action_ids": ["bad action"]}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_successful_usage_is_aggregated_and_idempotent(self):
        event_id = uuid4()
        first = self.usage("shoppingItem", event_id=event_id, origin_page="shopping", context_bucket="shopping")
        self.assertEqual(first.status_code, 201)
        self.assertFalse(first.data["deduplicated"])
        replay = self.usage("shoppingItem", event_id=event_id, origin_page="shopping", context_bucket="shopping")
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.data["deduplicated"])

        stat = CreateActionStat.objects.get(membership=self.membership, action_id="shoppingItem")
        self.assertEqual(stat.use_count, 1)
        self.assertEqual(stat.context_stats, {"shopping": 1})
        self.assertEqual(sum(stat.time_bucket_stats.values()), 1)
        self.assertEqual(CreateActionUsageReceipt.objects.filter(membership=self.membership).count(), 1)

    def test_usage_rejects_failure_and_domain_content(self):
        failed = self.usage("task", success=False)
        self.assertEqual(failed.status_code, 400)
        content = self.usage("task", title="Private title")
        self.assertEqual(content.status_code, 400)
        self.assertFalse(CreateActionStat.objects.exists())
        self.assertFalse(CreateActionUsageReceipt.objects.exists())

    def test_usage_receipt_cannot_be_reused_across_memberships(self):
        event_id = uuid4()
        self.assertEqual(self.usage("task", event_id=event_id).status_code, 201)
        second_family = Family.objects.create(name="Alice Second", slug="alice-second", timezone="Europe/Berlin")
        Membership.objects.create(family=second_family, user=self.alice, role=Membership.Role.ADULT)
        response = self.usage("task", family=second_family, event_id=event_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(CreateActionStat.objects.filter(action_id="task").count(), 1)

    def test_global_scope_aggregates_only_same_user_active_families_and_reset_clears_it(self):
        second_family = Family.objects.create(name="Alice Global", slug="alice-global", timezone="Europe/Berlin")
        second_membership = Membership.objects.create(family=second_family, user=self.alice, role=Membership.Role.ADULT)
        self.assertEqual(self.usage("event").status_code, 201)
        self.assertEqual(self.usage("event", family=second_family).status_code, 201)
        response = self.client.patch(self.url(), {"learning_scope": "global"}, format="json")
        self.assertEqual(response.status_code, 200)
        event_stat = next(row for row in response.data["stats"] if row["action_id"] == "event")
        self.assertEqual(event_stat["use_count"], 2)

        reset = self.client.patch(self.url(), {"reset_learning": True}, format="json")
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.data["stats"], [])
        self.assertFalse(CreateActionStat.objects.filter(membership__in=[self.membership, second_membership]).exists())

    def test_foreign_family_is_denied_without_creating_preferences(self):
        response = self.client.get(self.url(self.other))
        self.assertEqual(response.status_code, 403)
        response = self.client.patch(self.url(self.other), {"smart_ranking_enabled": False}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CreateActionPreference.objects.filter(membership=self.other_membership).exists())

    def test_shared_browser_cookie_switch_cannot_read_patch_or_replay_previous_membership(self):
        Membership.objects.create(family=self.family, user=self.bob, role=Membership.Role.ADULT)
        self.client.force_authenticate(self.bob)
        self.client.credentials(HTTP_X_CREATE_MEMBERSHIP=str(self.membership.pk))
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.patch(self.url(), {"direct_mode": True}, format="json").status_code, 403)
        self.assertEqual(self.usage().status_code, 403)
        self.assertFalse(CreateActionPreference.objects.exists())
        self.assertFalse(CreateActionStat.objects.exists())
        self.assertFalse(CreateActionUsageReceipt.objects.exists())

    def test_verified_membership_header_accepts_own_profile(self):
        self.client.credentials(HTTP_X_CREATE_MEMBERSHIP=str(self.membership.pk))
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertEqual(self.usage().status_code, 201)
