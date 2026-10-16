from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership

from .models import QuizRound


User = get_user_model()


class QuizRandomOrderTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Quiz Random Familie", slug="quiz-random", locale="de")
        self.alice = User.objects.create_user(username="quiz-random-alice", password="test")
        self.bob = User.objects.create_user(username="quiz-random-bob", password="test")
        self.alice_member = Membership.objects.create(family=self.family, user=self.alice, display_name="Alice")
        self.bob_member = Membership.objects.create(family=self.family, user=self.bob, display_name="Bob")
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_quiz_chooses_from_remaining_questions_and_never_repeats_within_match(self):
        candidate_sets = []

        def choose_last(candidates):
            candidate_sets.append(tuple(candidates))
            return candidates[-1]

        self.auth(self.alice)
        created = self.client.post(
            "/api/games/",
            {
                "family": str(self.family.id),
                "opponent": str(self.bob_member.id),
                "game_type": "quiz",
                "round_count": 3,
                "quiz_mode": "mixed",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        match_id = created.data["id"]

        with patch("games.services.secrets.choice", side_effect=choose_last):
            self.auth(self.bob)
            accepted = self.client.post(f"/api/games/{match_id}/accept/", {}, format="json")
            self.assertEqual(accepted.status_code, 200, accepted.data)
            first_round = QuizRound.objects.get(match_id=match_id, number=1)

            self.auth(self.alice)
            answer = first_round.question.correct_index
            first = self.client.post(f"/api/games/{match_id}/quiz/answer/", {"answer": answer}, format="json")
            self.assertEqual(first.status_code, 200, first.data)
            self.auth(self.bob)
            second = self.client.post(f"/api/games/{match_id}/quiz/answer/", {"answer": answer}, format="json")
            self.assertEqual(second.status_code, 200, second.data)

        second_round = QuizRound.objects.get(match_id=match_id, number=2)
        self.assertGreaterEqual(len(candidate_sets), 2)
        self.assertIn(first_round.question_id, candidate_sets[0])
        self.assertNotIn(first_round.question_id, candidate_sets[1])
        self.assertNotEqual(first_round.question_id, second_round.question_id)
