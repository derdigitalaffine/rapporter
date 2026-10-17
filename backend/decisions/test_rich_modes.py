from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership

from .models import DecisionVote


class DecisionRichModeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="decision-rich-owner")
        self.adult = User.objects.create_user(username="decision-rich-adult")
        self.family = Family.objects.create(name="Decision Rich Family", slug="decision-rich-family")
        self.owner_membership = Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Alex",
        )
        self.adult_membership = Membership.objects.create(
            family=self.family,
            user=self.adult,
            role=Membership.Role.ADULT,
            display_name="Sam",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def create_decision(self, mode):
        response = self.client.post(
            "/api/decisions/",
            {
                "family": str(self.family.id),
                "question": "Welche Option passt am besten?",
                "mode": mode,
                "anonymous": False,
                "options": ["A", "B", "C"],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_ranking_requires_complete_order_and_preserves_order(self):
        decision = self.create_decision("ranking")
        option_ids = [row["id"] for row in decision["options"]]
        adult = self.client_for(self.adult)

        incomplete = adult.post(
            f"/api/decisions/{decision['id']}/vote/",
            {"family": str(self.family.id), "option_ids": option_ids[:2]},
            format="json",
        )
        self.assertEqual(incomplete.status_code, 400, incomplete.data)
        self.assertEqual(incomplete.data["code"], "ranking_requires_all_options")

        ordered = [option_ids[1], option_ids[0], option_ids[2]]
        voted = adult.post(
            f"/api/decisions/{decision['id']}/vote/",
            {"family": str(self.family.id), "option_ids": ordered},
            format="json",
        )
        self.assertEqual(voted.status_code, 200, voted.data)
        self.assertEqual(voted.data["my_option_ids"], ordered)
        by_id = {row["id"]: row for row in voted.data["options"]}
        self.assertEqual(by_id[ordered[0]]["my_rank"], 1)
        self.assertEqual(by_id[ordered[0]]["average_rank"], 1.0)
        self.assertEqual(voted.data["result"]["winner"]["id"], ordered[0])

        cleared = adult.post(
            f"/api/decisions/{decision['id']}/vote/",
            {"family": str(self.family.id), "option_ids": []},
            format="json",
        )
        self.assertEqual(cleared.status_code, 200, cleared.data)
        self.assertEqual(cleared.data["my_option_ids"], [])
        self.assertFalse(
            DecisionVote.objects.filter(decision_id=decision["id"], member=self.adult_membership).exists()
        )

    def test_rating_accepts_one_to_five_and_aggregates(self):
        decision = self.create_decision("rating")
        first, second, third = [row["id"] for row in decision["options"]]
        adult = self.client_for(self.adult)

        adult_vote = adult.post(
            f"/api/decisions/{decision['id']}/vote/",
            {
                "family": str(self.family.id),
                "ratings": [
                    {"option_id": first, "score": 5},
                    {"option_id": second, "score": 3},
                ],
            },
            format="json",
        )
        self.assertEqual(adult_vote.status_code, 200, adult_vote.data)
        by_id = {row["id"]: row for row in adult_vote.data["options"]}
        self.assertEqual(by_id[first]["my_score"], 5)
        self.assertEqual(by_id[first]["average_score"], 5.0)
        self.assertIsNone(by_id[third]["average_score"])
        self.assertEqual(adult_vote.data["result"]["winner"]["id"], first)

        owner_vote = self.client.post(
            f"/api/decisions/{decision['id']}/vote/",
            {
                "family": str(self.family.id),
                "ratings": [
                    {"option_id": first, "score": 1},
                    {"option_id": second, "score": 5},
                ],
            },
            format="json",
        )
        self.assertEqual(owner_vote.status_code, 200, owner_vote.data)
        by_id = {row["id"]: row for row in owner_vote.data["options"]}
        self.assertEqual(by_id[first]["average_score"], 3.0)
        self.assertEqual(by_id[second]["average_score"], 4.0)
        self.assertEqual(owner_vote.data["result"]["winner"]["id"], second)

        invalid = adult.post(
            f"/api/decisions/{decision['id']}/vote/",
            {"family": str(self.family.id), "ratings": [{"option_id": third, "score": 6}]},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)

        cleared = adult.post(
            f"/api/decisions/{decision['id']}/vote/",
            {"family": str(self.family.id), "ratings": []},
            format="json",
        )
        self.assertEqual(cleared.status_code, 200, cleared.data)
        self.assertFalse(
            DecisionVote.objects.filter(decision_id=decision["id"], member=self.adult_membership).exists()
        )
