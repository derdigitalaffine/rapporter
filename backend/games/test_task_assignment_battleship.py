from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership, Task

from .models import BattleshipBoard, GameMatch


User = get_user_model()


class BattleshipTaskAssignmentTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Muster", slug="battleship-task-muster", locale="de")
        self.alice = User.objects.create_user(username="alice-battleship-task", password="test")
        self.bob = User.objects.create_user(username="bob-battleship-task", password="test")
        self.alice_member = Membership.objects.create(family=self.family, user=self.alice, display_name="Alice")
        self.bob_member = Membership.objects.create(family=self.family, user=self.bob, display_name="Bob")
        self.task = Task.objects.create(family=self.family, title="Spülmaschine", created_by=self.alice)
        self.client = APIClient()

    def test_battleship_finish_applies_same_consented_loser_rule(self):
        self.client.force_authenticate(user=self.alice)
        created = self.client.post(
            "/api/games/",
            {
                "family": str(self.family.id),
                "opponent": str(self.bob_member.id),
                "game_type": "battleship",
                "task_assignment": {"task": str(self.task.id), "rule": "loser", "confirmed": True},
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)

        self.client.force_authenticate(user=self.bob)
        accepted = self.client.post(
            f"/api/games/{created.data['id']}/accept/",
            {"task_assignment_confirmed": True},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)

        match = GameMatch.objects.get(id=created.data["id"])
        BattleshipBoard.objects.create(match=match, player=self.alice_member, ships=[], confirmed=True)
        BattleshipBoard.objects.create(
            match=match,
            player=self.bob_member,
            ships=[{"cells": [[0, 0]]}],
            confirmed=True,
        )
        match.current_turn = self.alice_member
        match.save(update_fields=["current_turn", "updated_at"])

        self.client.force_authenticate(user=self.alice)
        finished = self.client.post(
            f"/api/games/{created.data['id']}/battleship/fire/",
            {"x": 0, "y": 0},
            format="json",
        )
        self.assertEqual(finished.status_code, 200, finished.data)
        self.assertEqual(finished.data["status"], "finished")
        self.assertEqual(finished.data["winner"]["id"], str(self.alice_member.id))
        self.assertEqual(finished.data["task_assignment"]["outcome"], "applied")

        self.task.refresh_from_db()
        self.assertEqual(self.task.assignee_id, self.bob.id)
