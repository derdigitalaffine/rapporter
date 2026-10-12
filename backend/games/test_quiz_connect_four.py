from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership

from .models import GameMatch, QuizQuestion, QuizRound


User = get_user_model()


class QuizAndConnectFourApiTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Quiz Familie", slug="quiz-games", locale="de")
        self.alice = User.objects.create_user(username="quiz-alice", password="test")
        self.bob = User.objects.create_user(username="quiz-bob", password="test")
        self.alice_member = Membership.objects.create(family=self.family, user=self.alice, display_name="Alice")
        self.bob_member = Membership.objects.create(family=self.family, user=self.bob, display_name="Bob")
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def challenge(self, game_type, **extra):
        self.auth(self.alice)
        payload = {
            "family": str(self.family.id),
            "opponent": str(self.bob_member.id),
            "game_type": game_type,
            **extra,
        }
        response = self.client.post("/api/games/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def accept(self, match_id):
        self.auth(self.bob)
        response = self.client.post(f"/api/games/{match_id}/accept/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_quiz_question_bank_is_persisted_for_all_modes(self):
        self.assertGreaterEqual(QuizQuestion.objects.filter(mode=GameMatch.QuizMode.MIXED, active=True).count(), 7)
        self.assertGreaterEqual(QuizQuestion.objects.filter(mode=GameMatch.QuizMode.PHYSICS_EXPERT, active=True).count(), 7)
        self.assertGreaterEqual(QuizQuestion.objects.filter(mode=GameMatch.QuizMode.CHEMISTRY_EXPERT, active=True).count(), 7)

    def test_quiz_keeps_solution_and_answers_private_until_both_submit(self):
        created = self.challenge("quiz", round_count=3, quiz_mode="physics_expert")
        match_id = created["id"]
        accepted = self.accept(match_id)
        self.assertEqual(accepted["quiz"]["mode"], "physics_expert")
        current = accepted["quiz"]["rounds"][0]
        self.assertNotIn("correct_answer", current)
        self.assertIsNone(current["my_answer"])
        self.assertTrue(current["prompt"])
        self.assertEqual(len(current["options"]), 4)
        round_row = QuizRound.objects.get(match_id=match_id, number=1)
        self.assertEqual(round_row.question.mode, GameMatch.QuizMode.PHYSICS_EXPERT)

        self.auth(self.alice)
        first = self.client.post(f"/api/games/{match_id}/quiz/answer/", {"answer": 0}, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        hidden = first.data["quiz"]["rounds"][0]
        self.assertTrue(hidden["submitted_by_me"])
        self.assertFalse(hidden["resolved"])
        self.assertIsNone(hidden["my_answer"])
        self.assertNotIn("correct_answer", hidden)

        self.auth(self.bob)
        before = self.client.get(f"/api/games/{match_id}/")
        opponent_view = before.data["quiz"]["rounds"][0]
        self.assertTrue(opponent_view["opponent_submitted"])
        self.assertIsNone(opponent_view["opponent_answer"])
        self.assertNotIn("correct_answer", opponent_view)

        resolved = self.client.post(f"/api/games/{match_id}/quiz/answer/", {"answer": 1}, format="json")
        self.assertEqual(resolved.status_code, 200, resolved.data)
        solved = resolved.data["quiz"]["rounds"][0]
        self.assertTrue(solved["resolved"])
        self.assertIn("correct_answer", solved)
        self.assertIn("explanation", solved)
        self.assertEqual(solved["my_answer"], 1)
        self.assertEqual(solved["opponent_answer"], 0)
        self.assertEqual(resolved.data["quiz"]["current_round"], 2)

    def test_quiz_validates_mode_rounds_and_finishes_by_score(self):
        self.auth(self.alice)
        invalid_mode = self.client.post(
            "/api/games/",
            {
                "family": str(self.family.id),
                "opponent": str(self.bob_member.id),
                "game_type": "quiz",
                "round_count": 5,
                "quiz_mode": "unsafe_lab",
            },
            format="json",
        )
        self.assertEqual(invalid_mode.status_code, 400)
        self.assertEqual(invalid_mode.data["code"], "invalid_quiz_mode")
        for rounds in (2, 8):
            invalid_rounds = self.client.post(
                "/api/games/",
                {
                    "family": str(self.family.id),
                    "opponent": str(self.bob_member.id),
                    "game_type": "quiz",
                    "round_count": rounds,
                    "quiz_mode": "chemistry_expert",
                },
                format="json",
            )
            self.assertEqual(invalid_rounds.status_code, 400)

        created = self.challenge("quiz", round_count=3, quiz_mode="mixed")
        match_id = created["id"]
        self.accept(match_id)
        for number in range(1, 4):
            question = QuizRound.objects.get(match_id=match_id, number=number).question
            self.auth(self.alice)
            alice = self.client.post(
                f"/api/games/{match_id}/quiz/answer/",
                {"answer": question.correct_index},
                format="json",
            )
            self.assertEqual(alice.status_code, 200, alice.data)
            self.auth(self.bob)
            wrong = (question.correct_index + 1) % len(question.options_de)
            bob = self.client.post(f"/api/games/{match_id}/quiz/answer/", {"answer": wrong}, format="json")
            self.assertEqual(bob.status_code, 200, bob.data)
        self.assertEqual(bob.data["status"], "finished")
        self.assertEqual(bob.data["winner"]["id"], str(self.alice_member.id))
        self.assertEqual(bob.data["quiz"]["my_score"], 0)
        self.assertEqual(bob.data["quiz"]["opponent_score"], 3)

    def test_connect_four_enforces_turns_full_columns_and_vertical_win(self):
        created = self.challenge("connect_four")
        match_id = created["id"]
        accepted = self.accept(match_id)
        self.assertFalse(accepted["is_my_turn"])

        not_bobs_turn = self.client.post(f"/api/games/{match_id}/connect-four/drop/", {"column": 1}, format="json")
        self.assertEqual(not_bobs_turn.status_code, 409)
        self.assertEqual(not_bobs_turn.data["code"], "not_your_turn")

        for actor, column in [
            (self.alice, 0),
            (self.bob, 1),
            (self.alice, 0),
            (self.bob, 1),
            (self.alice, 0),
            (self.bob, 1),
            (self.alice, 0),
        ]:
            self.auth(actor)
            response = self.client.post(f"/api/games/{match_id}/connect-four/drop/", {"column": column}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "finished")
        self.assertEqual(response.data["winner"]["id"], str(self.alice_member.id))
        self.assertEqual(len(response.data["connect_four"]["moves"]), 7)

        full = self.challenge("connect_four")
        full_id = full["id"]
        self.accept(full_id)
        for actor in (self.alice, self.bob, self.alice, self.bob, self.alice, self.bob):
            self.auth(actor)
            response = self.client.post(f"/api/games/{full_id}/connect-four/drop/", {"column": 6}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
        self.auth(self.alice)
        blocked = self.client.post(f"/api/games/{full_id}/connect-four/drop/", {"column": 6}, format="json")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data["code"], "column_full")

    def test_connect_four_rejects_invalid_columns(self):
        created = self.challenge("connect_four")
        self.accept(created["id"])
        self.auth(self.alice)
        for column in (-1, 7, True, "2"):
            response = self.client.post(
                f"/api/games/{created['id']}/connect-four/drop/",
                {"column": column},
                format="json",
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.data["code"], "invalid_column")
