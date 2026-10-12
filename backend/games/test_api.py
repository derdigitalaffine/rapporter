from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership
from notifications.models import Notification

from .models import GameMatch


User = get_user_model()


class GamesApiTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Muster", slug="games-muster", locale="de")
        self.alice = User.objects.create_user(username="alice-games", password="test")
        self.bob = User.objects.create_user(username="bob-games", password="test")
        self.carol = User.objects.create_user(username="carol-games", password="test")
        self.alice_member = Membership.objects.create(family=self.family, user=self.alice, display_name="Alice")
        self.bob_member = Membership.objects.create(family=self.family, user=self.bob, display_name="Bob")
        other = Family.objects.create(name="Andere", slug="games-other")
        self.carol_member = Membership.objects.create(family=other, user=self.carol, display_name="Carol")
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def challenge(self, game_type="rps", round_count=3):
        self.auth(self.alice)
        response = self.client.post(
            "/api/games/",
            {"family": str(self.family.id), "opponent": str(self.bob_member.id), "game_type": game_type, "round_count": round_count},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def accept(self, match_id):
        self.auth(self.bob)
        response = self.client.post(f"/api/games/{match_id}/accept/", {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_rps_validates_one_to_five_rounds_and_keeps_choices_private(self):
        for invalid in (0, 6):
            self.auth(self.alice)
            response = self.client.post(
                "/api/games/",
                {"family": str(self.family.id), "opponent": str(self.bob_member.id), "game_type": "rps", "round_count": invalid},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["code"], "invalid_round_count")

        created = self.challenge("rps", 1)
        match_id = created["id"]
        self.assertTrue(Notification.objects.filter(recipient=self.bob_member, event_type="games.challenge").exists())
        self.accept(match_id)

        self.auth(self.alice)
        first = self.client.post(f"/api/games/{match_id}/rps/choice/", {"choice": "rock"}, format="json")
        self.assertEqual(first.status_code, 200, first.data)
        round_row = first.data["rps"]["rounds"][0]
        self.assertTrue(round_row["submitted_by_me"])
        self.assertFalse(round_row["resolved"])
        self.assertIsNone(round_row["my_choice"])
        turn_count = Notification.objects.filter(recipient=self.bob_member, event_type="games.turn").count()

        duplicate = self.client.post(f"/api/games/{match_id}/rps/choice/", {"choice": "paper"}, format="json")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(Notification.objects.filter(recipient=self.bob_member, event_type="games.turn").count(), turn_count)

        self.auth(self.bob)
        before = self.client.get(f"/api/games/{match_id}/")
        self.assertTrue(before.data["rps"]["rounds"][0]["opponent_submitted"])
        self.assertIsNone(before.data["rps"]["rounds"][0]["opponent_choice"])
        resolved = self.client.post(f"/api/games/{match_id}/rps/choice/", {"choice": "scissors"}, format="json")
        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertEqual(resolved.data["status"], "finished")
        final_round = resolved.data["rps"]["rounds"][0]
        self.assertEqual(final_round["my_choice"], "scissors")
        self.assertEqual(final_round["opponent_choice"], "rock")
        self.assertEqual(resolved.data["winner"]["id"], str(self.alice_member.id))

    def test_rps_runs_exact_configured_round_count(self):
        created = self.challenge("rps", 5)
        match_id = created["id"]
        self.accept(match_id)
        for index in range(5):
            self.auth(self.alice)
            response = self.client.post(f"/api/games/{match_id}/rps/choice/", {"choice": "rock"}, format="json")
            self.assertEqual(response.status_code, 200)
            self.auth(self.bob)
            response = self.client.post(f"/api/games/{match_id}/rps/choice/", {"choice": "rock"}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["status"], "finished" if index == 4 else "active")
        self.assertTrue(response.data["is_draw"])
        self.assertEqual(len(response.data["rps"]["rounds"]), 5)

    def test_non_participant_cannot_read_or_mutate_match(self):
        created = self.challenge("rps", 3)
        self.auth(self.carol)
        response = self.client.get(f"/api/games/{created['id']}/")
        self.assertEqual(response.status_code, 404)
        response = self.client.post(f"/api/games/{created['id']}/accept/", {}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_battleship_hides_opponent_fleet_and_enforces_turns(self):
        created = self.challenge("battleship", 1)
        match_id = created["id"]
        self.accept(match_id)
        alice_fleet = [
            {"cells": [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]]},
            {"cells": [[0, 1], [1, 1], [2, 1], [3, 1]]},
            {"cells": [[0, 2], [1, 2], [2, 2]]},
            {"cells": [[0, 3], [1, 3], [2, 3]]},
            {"cells": [[0, 4], [1, 4]]},
        ]
        bob_fleet = [
            {"cells": [[5, 9], [6, 9], [7, 9], [8, 9], [9, 9]]},
            {"cells": [[6, 8], [7, 8], [8, 8], [9, 8]]},
            {"cells": [[7, 7], [8, 7], [9, 7]]},
            {"cells": [[7, 6], [8, 6], [9, 6]]},
            {"cells": [[8, 5], [9, 5]]},
        ]
        self.auth(self.alice)
        response = self.client.post(f"/api/games/{match_id}/battleship/fleet/", {"ships": alice_fleet}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.auth(self.bob)
        before = self.client.get(f"/api/games/{match_id}/")
        self.assertEqual(before.data["battleship"]["my_ships"], [])
        self.assertNotIn("opponent_ships", before.data["battleship"])
        response = self.client.post(f"/api/games/{match_id}/battleship/fleet/", {"ships": bob_fleet}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["battleship"]["my_ships"], bob_fleet)
        self.assertNotIn("opponent_ships", response.data["battleship"])

        not_bobs_turn = self.client.post(f"/api/games/{match_id}/battleship/fire/", {"x": 0, "y": 0}, format="json")
        self.assertEqual(not_bobs_turn.status_code, 409)
        self.auth(self.alice)
        shot = self.client.post(f"/api/games/{match_id}/battleship/fire/", {"x": 9, "y": 9}, format="json")
        self.assertEqual(shot.status_code, 200, shot.data)
        self.assertEqual(shot.data["battleship"]["shots"][-1]["result"], "hit")
        self.assertFalse(shot.data["is_my_turn"])

        self.auth(self.bob)
        reply = self.client.post(f"/api/games/{match_id}/battleship/fire/", {"x": 9, "y": 9}, format="json")
        self.assertEqual(reply.status_code, 200, reply.data)
        self.auth(self.alice)
        repeat = self.client.post(f"/api/games/{match_id}/battleship/fire/", {"x": 9, "y": 9}, format="json")
        self.assertEqual(repeat.status_code, 409)
        self.assertEqual(repeat.data["code"], "coordinate_already_fired")

    def test_battleship_rejects_invalid_fleet(self):
        created = self.challenge("battleship", 1)
        self.accept(created["id"])
        self.auth(self.alice)
        invalid = [
            {"cells": [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4]]},
            {"cells": [[0, 1], [1, 1], [2, 1], [3, 1]]},
            {"cells": [[0, 2], [1, 2], [2, 2]]},
            {"cells": [[0, 3], [1, 3], [2, 3]]},
            {"cells": [[0, 4], [1, 4]]},
        ]
        response = self.client.post(f"/api/games/{created['id']}/battleship/fleet/", {"ships": invalid}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "invalid_fleet")

    def test_challenge_requires_same_family_opponent(self):
        self.auth(self.alice)
        response = self.client.post(
            "/api/games/",
            {"family": str(self.family.id), "opponent": str(self.carol_member.id), "game_type": "rps", "round_count": 3},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(GameMatch.objects.count(), 0)
