import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from auth_identity.service import create_primary_identity
from family.models import Family, Membership, Task
from messenger.models import Friendship
from .models import GameMatch, QuizQuestion


class PersonalDuelTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Duel One", slug="duel-one")
        self.other = Family.objects.create(name="Duel Two", slug="duel-two")
        self.one = self.user("duel-one", self.family)
        self.two = self.user("duel-two", self.other)
        self.owner = self.user("duel-owner", self.family, "owner")
        self.friend = Friendship.objects.create(low_user=self.one, high_user=self.two)
        self.client = APIClient()
        self.client.force_authenticate(self.one)

    def user(self, name, family, role="adult"):
        user = get_user_model().objects.create_user(username=name, email=name + "@example.com")
        create_primary_identity(user, user.email, verified=True)
        Membership.objects.create(user=user, family=family, role=role, display_name=name)
        return user

    def create(self, game_type, **extra):
        return self.client.post("/api/games/", {"friendship": str(self.friend.pk), "game_type": game_type, **extra}, format="json")

    def action(self, match, route, data=None):
        return self.client.post(f'/api/games/{match["id"]}/{route}/', data or {}, format="json")

    def accept(self, match):
        self.client.force_authenticate(self.two)
        response = self.action(match, "accept")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_rps_uses_same_engine_hides_choice_and_finishes_without_family_stake(self):
        response = self.create("rps", round_count=1)
        self.assertEqual(response.status_code, 201, response.data)
        match = self.accept(response.data)
        self.action(match, "rps/choice", {"choice": "scissors"})
        self.client.force_authenticate(self.one)
        detail = self.client.get(f'/api/games/{match["id"]}/').data
        self.assertIsNone(detail["rps"]["rounds"][0]["opponent_choice"])
        finished = self.action(match, "rps/choice", {"choice": "rock"})
        self.assertEqual(finished.data["status"], "finished")
        self.assertEqual(finished.data["winner"]["id"], f"u:{self.one.pk}")
        self.assertIsNone(finished.data["family"])
        self.assertIsNone(finished.data["task_assignment"])
        self.assertFalse(Membership.objects.filter(user=self.two, family=self.family).exists())

    def test_owner_nonparticipant_and_wrong_friendship_cannot_read_or_mutate(self):
        match = self.create("rps").data
        self.client.force_authenticate(self.owner)
        for route in ("accept", "decline", "cancel", "rps/choice", "quiz/answer", "connect-four/drop", "battleship/fleet", "battleship/fire"):
            self.assertEqual(self.action(match, route).status_code, 404)
        self.assertEqual(self.client.get(f'/api/games/{match["id"]}/').status_code, 404)
        self.assertEqual(self.client.get(f"/api/games/?friendship={self.friend.pk}").status_code, 404)
        self.assertEqual(self.create("rps").status_code, 404)

    def test_friendship_never_grants_family_task_or_existing_game_access(self):
        task = Task.objects.create(family=self.family, title="Private family task")
        self.assertEqual(self.create("rps", task_assignment={"task": str(task.pk), "confirmed": True, "rule": "loser"}).status_code, 400)
        self.assertEqual(self.create("rps", family=str(self.family.pk)).status_code, 400)
        member = Membership.objects.get(user=self.one)
        opponent = Membership.objects.get(user=self.owner)
        family_game = GameMatch.objects.create(family=self.family, challenger=member, opponent=opponent, game_type="rps")
        self.client.force_authenticate(self.two)
        self.assertEqual(self.client.get(f'/api/games/{family_game.pk}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/games/?family={self.family.pk}').status_code, 404)
        self.assertEqual(self.client.get(f'/api/tasks/?family={self.family.pk}').status_code, 403)

    def test_connect_four_personal_turns_and_win(self):
        match = self.accept(self.create("connect_four").data)
        for i in range(7):
            self.client.force_authenticate(self.one if i % 2 == 0 else self.two)
            response = self.action(match, "connect-four/drop", {"column": 0 if i % 2 == 0 else 1})
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "finished")
        self.assertEqual(response.data["winner"]["id"], f"u:{self.one.pk}")

    def test_battleship_personal_boards_hide_opponent_fleet(self):
        match = self.accept(self.create("battleship").data)
        ships = [{"cells": [[x, y] for x in range(size)]} for y, size in enumerate([5, 4, 3, 3, 2])]
        self.assertEqual(self.action(match, "battleship/fleet", {"ships": ships}).status_code, 200)
        self.client.force_authenticate(self.one)
        detail = self.client.get(f'/api/games/{match["id"]}/').data
        self.assertEqual(detail["battleship"]["my_ships"], [])
        self.assertNotIn("opponent_ships", detail["battleship"])
        self.action(match, "battleship/fleet", {"ships": ships})
        fired = self.action(match, "battleship/fire", {"x": 0, "y": 0})
        self.assertEqual(fired.status_code, 200, fired.data)
        self.assertEqual(fired.data["battleship"]["shots"][0]["result"], "hit")

    def test_quiz_personal_answers_stay_hidden_until_both_submit(self):
        for i in range(3):
            QuizQuestion.objects.create(mode="mixed", prompt_de=f"Frage {i}", prompt_en=f"Question {i}", options_de=["A", "B"], options_en=["A", "B"], correct_index=0)
        match = self.accept(self.create("quiz", round_count=3).data)
        for i in range(3):
            self.client.force_authenticate(self.two)
            self.action(match, "quiz/answer", {"answer": 1})
            self.client.force_authenticate(self.one)
            detail = self.client.get(f'/api/games/{match["id"]}/').data
            self.assertNotIn("correct_answer", detail["quiz"]["rounds"][i])
            response = self.action(match, "quiz/answer", {"answer": 0})
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "finished")

    def test_remove_block_or_inactive_user_revokes_all_game_actions(self):
        for action in ("remove", "block"):
            self.client.force_authenticate(self.one)
            match = self.create("rps").data
            self.accept(match)
            self.client.force_authenticate(self.one)
            self.client.post(f"/api/chat/contacts/{self.friend.pk}/", {"action": action}, format="json")
            self.assertEqual(self.action(match, "rps/choice", {"choice": "rock"}).status_code, 404)
            self.assertEqual(self.client.get(f'/api/games/{match["id"]}/').status_code, 404)
            if action == "remove":
                self.friend.active = True
                self.friend.save()

    def test_database_rejects_combined_personal_and_family_scope(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            GameMatch.objects.create(friendship=self.friend, challenger_user=self.one, opponent_user=self.two, family=self.family, game_type="rps")
