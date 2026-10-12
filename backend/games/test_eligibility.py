from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from family.models import Family, Membership, Task
from notifications.models import Notification

from .models import GameMatch, GameTaskAssignment
from .services import apply_task_assignment


class GameEligibilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="eligible-alice")
        self.bob = User.objects.create_user(username="eligible-bob")
        self.family = Family.objects.create(name="Players", slug="eligible-players")
        self.alice_member = Membership.objects.create(family=self.family, user=self.alice, role="owner")
        self.bob_member = Membership.objects.create(family=self.family, user=self.bob, role="child")
        self.task = Task.objects.create(family=self.family, title="Shared task", created_by=self.alice)
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def challenge(self, *, stake=False, opponent=None):
        payload = {"family": str(self.family.id), "opponent": str(opponent or self.bob_member.id), "game_type": "rps", "round_count": 1}
        if stake:
            payload["task_assignment"] = {"task": str(self.task.id), "rule": "winner", "confirmed": True}
        return self.client.post("/api/games/", payload, format="json")

    def assert_no_side_effects(self):
        self.assertFalse(GameMatch.objects.exists())
        self.assertFalse(GameTaskAssignment.objects.exists())
        self.assertFalse(Notification.objects.filter(event_type__startswith="games.").exists())
        self.task.refresh_from_db()
        self.assertIsNone(self.task.assignee_id)

    def test_inactive_opponent_is_neutral_and_never_creates_match_stake_or_notification(self):
        self.bob.is_active = False
        self.bob.save(update_fields=["is_active"])
        for stake in (False, True):
            with self.subTest(stake=stake):
                response = self.challenge(stake=stake)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.data, {"code": "opponent_unavailable"})
                self.assert_no_side_effects()

    def test_inactive_challenger_is_rejected_before_writes(self):
        self.alice.is_active = False
        self.alice.save(update_fields=["is_active"])
        response = self.challenge(stake=True)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {"code": "family_unavailable"})
        self.assert_no_side_effects()

    def test_missing_and_foreign_opponents_use_same_neutral_response(self):
        import uuid
        other = Family.objects.create(name="Other", slug="eligible-other")
        foreign = Membership.objects.create(family=other, user=self.bob)
        for opponent in (foreign.id, uuid.uuid4()):
            response = self.challenge(stake=True, opponent=opponent)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.data, {"code": "opponent_unavailable"})
            self.assert_no_side_effects()

    def test_active_child_remains_an_eligible_player(self):
        response = self.challenge(stake=True)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(GameTaskAssignment.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(event_type="games.challenge").count(), 1)

    def test_deactivated_challenger_cannot_be_accepted_or_notify(self):
        created = self.challenge(stake=True)
        self.assertEqual(created.status_code, 201, created.data)
        before = Notification.objects.count()
        self.alice.is_active = False
        self.alice.save(update_fields=["is_active"])
        self.client.force_authenticate(self.bob)
        response = self.client.post(f"/api/games/{created.data['id']}/accept/", {"task_assignment_confirmed": True}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data, {"code": "opponent_unavailable"})
        self.assertEqual(GameMatch.objects.get(id=created.data["id"]).status, GameMatch.Status.PENDING)
        self.assertIsNone(GameTaskAssignment.objects.get().opponent_confirmed_at)
        self.assertEqual(Notification.objects.count(), before)

    def test_deactivated_player_cannot_receive_task_outcome_after_consent(self):
        from django.utils import timezone
        created = self.challenge(stake=True)
        match = GameMatch.objects.get(id=created.data["id"])
        stake = GameTaskAssignment.objects.get(match=match)
        stake.opponent_confirmed_at = timezone.now()
        stake.save()
        self.bob.is_active = False
        self.bob.save(update_fields=["is_active"])
        match.status = GameMatch.Status.FINISHED
        match.winner = self.bob_member
        match.save()
        with transaction.atomic():
            apply_task_assignment(match)
        stake.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(stake.invalidation_reason, "task_unavailable")
        self.assertIsNone(stake.applied_at)
        self.assertIsNone(self.task.assignee_id)

    def test_roster_exposes_read_only_active_state_without_per_player_queries(self):
        self.bob.is_active = False
        self.bob.save(update_fields=["is_active"])
        with CaptureQueriesContext(connection) as small:
            response = self.client.get("/api/families/")
        self.assertEqual(response.status_code, 200)
        rows = response.data.get("results", []) if isinstance(response.data, dict) else response.data
        players = {row["user"]: row for row in rows[0]["memberships"]}
        self.assertTrue(players[self.alice.id]["is_active"])
        self.assertFalse(players[self.bob.id]["is_active"])
        User = get_user_model()
        for number in range(20):
            Membership.objects.create(family=self.family, user=User.objects.create_user(username=f"eligible-{number}"))
        with CaptureQueriesContext(connection) as large:
            response = self.client.get("/api/families/")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(large), len(small))
        response = self.client.patch(f"/api/memberships/{self.bob_member.id}/", {"is_active": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.bob.refresh_from_db()
        self.assertFalse(self.bob.is_active)

    def test_revoked_task_visibility_is_rechecked_on_list_detail_summary_and_mutation(self):
        created = self.challenge(stake=True)
        match_id = created.data["id"]
        self.task.hidden_from_user = self.alice
        self.task.save(update_fields=["hidden_from_user"])
        for path in (f"/api/games/?family={self.family.id}", f"/api/games/summary/?family={self.family.id}"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(self.task.title, str(response.data))
            self.assertNotIn(match_id, str(response.data))
        response = self.client.get(f"/api/games/{match_id}/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data, {"code": "match_unavailable"})
        response = self.client.post(f"/api/games/{match_id}/cancel/", {}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(GameMatch.objects.get(id=match_id).status, GameMatch.Status.PENDING)
        self.client.force_authenticate(self.bob)
        response = self.client.get(f"/api/games/{match_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["task_assignment"]["task"]["title"], self.task.title)
        response = self.client.post(f"/api/games/{match_id}/accept/", {"task_assignment_confirmed": True}, format="json")
        self.assertEqual(response.status_code, 409)

    def test_completed_stake_cannot_be_consented_or_applied(self):
        from django.utils import timezone
        created = self.challenge(stake=True)
        match_id = created.data["id"]
        self.task.completed_at = timezone.now()
        self.task.save(update_fields=["completed_at"])
        self.client.force_authenticate(self.bob)
        response = self.client.post(f"/api/games/{match_id}/accept/", {"task_assignment_confirmed": True}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data, {"code": "task_assignment_unavailable"})
        stake = GameTaskAssignment.objects.get(match_id=match_id)
        self.assertIsNone(stake.opponent_confirmed_at)
        stake.opponent_confirmed_at = timezone.now()
        stake.save()
        match = GameMatch.objects.get(id=match_id)
        match.status = GameMatch.Status.FINISHED
        match.winner = self.bob_member
        match.save()
        with transaction.atomic():
            apply_task_assignment(match)
        stake.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(stake.invalidation_reason, "task_unavailable")
        self.assertIsNone(stake.applied_at)
        self.assertIsNone(self.task.assignee_id)

    def test_exact_task_action_filter_keeps_canonical_acl_beyond_first_page(self):
        for number in range(60):
            Task.objects.create(family=self.family, title=f"Earlier {number}", created_by=self.alice, priority="high")
        path = f"/api/actions/?family={self.family.id}&scope=all&kind=tasks&task={self.task.id}"
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["actions"][0]["id"], f"task:{self.task.id}")
        self.assertIn("duel", [action["id"] for action in response.data["actions"][0]["allowed_actions"]])
        self.task.hidden_from_user = self.alice
        self.task.save(update_fields=["hidden_from_user"])
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["actions"], [])
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get(path).data["count"], 1)
