from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.models import Family, Membership
from games.models import GameMatch

from .models import DecisionTieBreak


class DecisionTieBreakTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="tie-owner")
        self.adult = User.objects.create_user(username="tie-adult")
        self.family = Family.objects.create(name="Tie Family", slug="tie-family")
        self.owner_member = Membership.objects.create(
            family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Alex"
        )
        self.adult_member = Membership.objects.create(
            family=self.family, user=self.adult, role=Membership.Role.ADULT, display_name="Sam"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def tied_decision(self, *, anonymous=False):
        created = self.client.post(
            "/api/decisions/",
            {
                "family": str(self.family.id),
                "question": "A oder B?",
                "anonymous": anonymous,
                "options": ["A", "B"],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        first, second = [row["id"] for row in created.data["options"]]
        self.client.post(
            f"/api/decisions/{created.data['id']}/vote/",
            {"family": str(self.family.id), "option_ids": [first]},
            format="json",
        )
        adult = self.client_for(self.adult)
        voted = adult.post(
            f"/api/decisions/{created.data['id']}/vote/",
            {"family": str(self.family.id), "option_ids": [second]},
            format="json",
        )
        self.assertEqual(voted.status_code, 200, voted.data)
        closed = self.client.post(
            f"/api/decisions/{created.data['id']}/close/",
            {"family": str(self.family.id)},
            format="json",
        )
        self.assertEqual(closed.status_code, 200, closed.data)
        self.assertTrue(closed.data["result"]["is_tie"])
        return created.data["id"], first, second

    def test_random_tie_break_is_server_side_persisted_and_idempotent(self):
        decision_id, first, _ = self.tied_decision()
        with patch("decisions.tiebreaks.secrets.choice", side_effect=lambda rows: rows[0]):
            resolved = self.client.post(
                f"/api/decisions/{decision_id}/tie-break/",
                {"family": str(self.family.id), "method": "random"},
                format="json",
            )
        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertTrue(resolved.data["result"]["is_tie"])
        self.assertEqual(resolved.data["result"]["resolution"]["method"], "random")
        self.assertEqual(resolved.data["result"]["resolution"]["winner"]["id"], first)
        with patch("decisions.tiebreaks.secrets.choice", side_effect=AssertionError("must not reroll")):
            repeated = self.client.post(
                f"/api/decisions/{decision_id}/tie-break/",
                {"family": str(self.family.id), "method": "random"},
                format="json",
            )
        self.assertEqual(repeated.status_code, 200, repeated.data)
        self.assertEqual(repeated.data["result"]["resolution"]["winner"]["id"], first)
        self.assertEqual(DecisionTieBreak.objects.filter(decision_id=decision_id).count(), 1)

    def test_two_voter_tie_can_be_resolved_by_existing_game_match(self):
        decision_id, first, _ = self.tied_decision()
        started = self.client.post(
            f"/api/decisions/{decision_id}/tie-break/",
            {"family": str(self.family.id), "method": "game", "game_type": "connect_four"},
            format="json",
        )
        self.assertEqual(started.status_code, 200, started.data)
        game = started.data["result"]["tie_break"]["game"]
        self.assertEqual(game["status"], "pending")
        match = GameMatch.objects.get(id=game["id"])
        self.assertEqual(match.challenger_id, self.owner_member.id)
        self.assertEqual(match.opponent_id, self.adult_member.id)
        self.assertIsNone(started.data["result"]["resolution"])

        match.status = GameMatch.Status.FINISHED
        match.winner = self.owner_member
        match.is_draw = False
        match.finished_at = timezone.now()
        match.save()

        detail = self.client.get(f"/api/decisions/{decision_id}/?family={self.family.id}")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["result"]["resolution"]["method"], "game")
        self.assertEqual(detail.data["result"]["resolution"]["winner"]["id"], first)

    def test_anonymous_tie_never_exposes_game_path(self):
        decision_id, _, _ = self.tied_decision(anonymous=True)
        detail = self.client.get(f"/api/decisions/{decision_id}/?family={self.family.id}")
        self.assertTrue(detail.data["result"]["tie_break"]["can_random"])
        self.assertFalse(detail.data["result"]["tie_break"]["game_eligible"])
        self.assertFalse(detail.data["result"]["tie_break"]["can_game"])
        denied = self.client.post(
            f"/api/decisions/{decision_id}/tie-break/",
            {"family": str(self.family.id), "method": "game", "game_type": "rps"},
            format="json",
        )
        self.assertEqual(denied.status_code, 409, denied.data)
        self.assertEqual(denied.data["code"], "game_tie_break_unavailable")

    def test_open_or_non_tied_decision_cannot_be_resolved(self):
        created = self.client.post(
            "/api/decisions/",
            {"family": str(self.family.id), "question": "Noch offen?", "options": ["A", "B"]},
            format="json",
        ).data
        response = self.client.post(
            f"/api/decisions/{created['id']}/tie-break/",
            {"family": str(self.family.id), "method": "random"},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "decision_still_open")
