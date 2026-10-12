from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership, Task

from .models import GameMatch, GameTaskAssignment


User = get_user_model()


class GameTaskAssignmentTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Muster", slug="duel-task-muster", locale="de")
        self.alice = User.objects.create_user(username="alice-duel-task", password="test")
        self.bob = User.objects.create_user(username="bob-duel-task", password="test")
        self.carol = User.objects.create_user(username="carol-duel-task", password="test")
        self.alice_member = Membership.objects.create(family=self.family, user=self.alice, display_name="Alice")
        self.bob_member = Membership.objects.create(family=self.family, user=self.bob, display_name="Bob")
        self.other_family = Family.objects.create(name="Andere", slug="duel-task-other")
        Membership.objects.create(family=self.other_family, user=self.carol, display_name="Carol")
        self.task = Task.objects.create(family=self.family, title="Müll rausbringen", created_by=self.alice)
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def challenge(self, *, rule="loser", game_type="rps", round_count=1, task=None, confirmed=True):
        self.auth(self.alice)
        response = self.client.post(
            "/api/games/",
            {
                "family": str(self.family.id),
                "opponent": str(self.bob_member.id),
                "game_type": game_type,
                "round_count": round_count,
                "task_assignment": {
                    "task": str((task or self.task).id),
                    "rule": rule,
                    "confirmed": confirmed,
                },
            },
            format="json",
        )
        return response

    def accept(self, match_id, *, confirmed=True):
        self.auth(self.bob)
        return self.client.post(
            f"/api/games/{match_id}/accept/",
            {"task_assignment_confirmed": confirmed},
            format="json",
        )

    def play_rps(self, match_id, alice_choice="rock", bob_choice="scissors"):
        self.auth(self.alice)
        first = self.client.post(f"/api/games/{match_id}/rps/choice/", {"choice": alice_choice}, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        self.auth(self.bob)
        return self.client.post(f"/api/games/{match_id}/rps/choice/", {"choice": bob_choice}, format="json")

    def test_task_stake_requires_explicit_consent_from_both_players(self):
        missing_challenger = self.challenge(confirmed=False)
        self.assertEqual(missing_challenger.status_code, 409)
        self.assertEqual(missing_challenger.data["code"], "task_assignment_consent_required")
        self.assertEqual(GameMatch.objects.count(), 0)

        created = self.challenge()
        self.assertEqual(created.status_code, 201, created.data)
        stake = created.data["task_assignment"]
        self.assertEqual(stake["task"]["id"], str(self.task.id))
        self.assertEqual(stake["rule"], "loser")
        self.assertTrue(stake["challenger_confirmed"])
        self.assertFalse(stake["opponent_confirmed"])
        self.assertEqual(stake["outcome"], "pending_consent")

        missing_opponent = self.accept(created.data["id"], confirmed=False)
        self.assertEqual(missing_opponent.status_code, 409)
        self.assertEqual(missing_opponent.data["code"], "task_assignment_consent_required")
        self.assertEqual(GameMatch.objects.get(id=created.data["id"]).status, GameMatch.Status.PENDING)

        accepted = self.accept(created.data["id"])
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertTrue(accepted.data["task_assignment"]["opponent_confirmed"])
        self.assertEqual(accepted.data["task_assignment"]["outcome"], "ready")

    def test_loser_rule_assigns_canonical_task_after_finished_rps(self):
        created = self.challenge(rule="loser")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.accept(created.data["id"]).status_code, 200)

        finished = self.play_rps(created.data["id"], "rock", "scissors")
        self.assertEqual(finished.status_code, 200, finished.data)
        self.assertEqual(finished.data["status"], "finished")
        self.task.refresh_from_db()
        self.assertEqual(self.task.assignee_id, self.bob.id)
        self.assertEqual(finished.data["task_assignment"]["outcome"], "applied")
        self.assertEqual(finished.data["task_assignment"]["applied_assignee_user_id"], self.bob.id)

        stake = GameTaskAssignment.objects.get(match_id=created.data["id"])
        applied_at = stake.applied_at
        self.auth(self.bob)
        detail = self.client.get(f"/api/games/{created.data['id']}/")
        self.assertEqual(detail.status_code, 200)
        stake.refresh_from_db()
        self.assertEqual(stake.applied_at, applied_at)
        self.assertEqual(self.task.assignee_id, self.bob.id)

    def test_winner_rule_can_reassign_an_existing_assignee(self):
        self.task.assignee = self.bob
        self.task.save()
        created = self.challenge(rule="winner")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.accept(created.data["id"]).status_code, 200)
        finished = self.play_rps(created.data["id"], "rock", "scissors")
        self.assertEqual(finished.status_code, 200, finished.data)
        self.task.refresh_from_db()
        self.assertEqual(self.task.assignee_id, self.alice.id)

    def test_assignment_change_after_consent_is_not_overwritten(self):
        created = self.challenge(rule="loser")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.accept(created.data["id"]).status_code, 200)
        self.task.assignee = self.alice
        self.task.save()

        finished = self.play_rps(created.data["id"], "rock", "scissors")
        self.assertEqual(finished.status_code, 200, finished.data)
        self.task.refresh_from_db()
        self.assertEqual(self.task.assignee_id, self.alice.id)
        stake = finished.data["task_assignment"]
        self.assertEqual(stake["outcome"], "invalidated")
        self.assertEqual(stake["invalidation_reason"], "task_assignment_changed")

    def test_assignment_change_before_opponent_consent_blocks_accept(self):
        created = self.challenge()
        self.assertEqual(created.status_code, 201, created.data)
        self.task.assignee = self.alice
        self.task.save()
        response = self.accept(created.data["id"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "task_assignment_changed")
        self.assertEqual(GameMatch.objects.get(id=created.data["id"]).status, GameMatch.Status.PENDING)

    def test_draw_never_assigns_task(self):
        created = self.challenge(rule="loser")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.accept(created.data["id"]).status_code, 200)
        finished = self.play_rps(created.data["id"], "rock", "rock")
        self.assertEqual(finished.status_code, 200, finished.data)
        self.task.refresh_from_db()
        self.assertIsNone(self.task.assignee_id)
        self.assertEqual(finished.data["task_assignment"]["outcome"], "draw")
        self.assertEqual(finished.data["task_assignment"]["invalidation_reason"], "draw")

    def test_cross_family_or_completed_task_cannot_be_staked(self):
        other_task = Task.objects.create(family=self.other_family, title="Geheim", created_by=self.carol)
        cross_family = self.challenge(task=other_task)
        self.assertEqual(cross_family.status_code, 404)
        self.assertEqual(cross_family.data["code"], "task_unavailable")

        from django.utils import timezone
        self.task.completed_at = timezone.now()
        self.task.save()
        completed = self.challenge()
        self.assertEqual(completed.status_code, 404)
        self.assertEqual(completed.data["code"], "task_unavailable")

    def test_standalone_games_remain_backward_compatible(self):
        self.auth(self.alice)
        created = self.client.post(
            "/api/games/",
            {"family": str(self.family.id), "opponent": str(self.bob_member.id), "game_type": "rps", "round_count": 1},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertIsNone(created.data["task_assignment"])
        self.auth(self.bob)
        accepted = self.client.post(f"/api/games/{created.data['id']}/accept/", {}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data["status"], "active")
