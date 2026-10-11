from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from family.context_models import ContextLink
from family.models import Family, FamilyEvent, Membership, Task
from family.notes_models import Note, NoteShare

from .models import Decision, DecisionVote


class DecisionApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="decision-owner")
        self.adult = User.objects.create_user(username="decision-adult")
        self.guest = User.objects.create_user(username="decision-guest")
        self.foreign = User.objects.create_user(username="decision-foreign")
        self.family = Family.objects.create(name="Decision Family", slug="decision-family")
        self.other_family = Family.objects.create(name="Other Family", slug="decision-other")
        self.owner_membership = Membership.objects.create(
            family=self.family, user=self.owner, role=Membership.Role.OWNER, display_name="Alex"
        )
        self.adult_membership = Membership.objects.create(
            family=self.family, user=self.adult, role=Membership.Role.ADULT, display_name="Sam"
        )
        self.guest_membership = Membership.objects.create(
            family=self.family, user=self.guest, role=Membership.Role.GUEST, display_name="Guest"
        )
        Membership.objects.create(
            family=self.other_family, user=self.foreign, role=Membership.Role.OWNER
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def create_decision(self, **overrides):
        payload = {
            "family": str(self.family.id),
            "question": "Samstag oder Sonntag?",
            "mode": "single",
            "anonymous": False,
            "options": ["Samstag", "Sonntag"],
        }
        payload.update(overrides)
        return self.client.post("/api/decisions/", payload, format="json")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_standalone_decision_and_single_vote_replace_semantics(self):
        created = self.create_decision()
        self.assertEqual(created.status_code, 201, created.data)
        decision_id = created.data["id"]
        first, second = [row["id"] for row in created.data["options"]]

        adult = self.client_for(self.adult)
        voted = adult.post(
            f"/api/decisions/{decision_id}/vote/",
            {"family": str(self.family.id), "option_ids": [first]},
            format="json",
        )
        self.assertEqual(voted.status_code, 200, voted.data)
        self.assertEqual(voted.data["my_option_ids"], [first])
        self.assertEqual(voted.data["total_voters"], 1)

        replaced = adult.post(
            f"/api/decisions/{decision_id}/vote/",
            {"family": str(self.family.id), "option_ids": [second]},
            format="json",
        )
        self.assertEqual(replaced.status_code, 200, replaced.data)
        self.assertEqual(replaced.data["my_option_ids"], [second])
        self.assertEqual(DecisionVote.objects.filter(decision_id=decision_id, member=self.adult_membership).count(), 1)

        cleared = adult.post(
            f"/api/decisions/{decision_id}/vote/",
            {"family": str(self.family.id), "option_ids": []},
            format="json",
        )
        self.assertEqual(cleared.status_code, 200, cleared.data)
        self.assertEqual(cleared.data["my_option_ids"], [])
        self.assertFalse(DecisionVote.objects.filter(decision_id=decision_id, member=self.adult_membership).exists())

    def test_multiple_choice_and_invalid_single_selection(self):
        single = self.create_decision().data
        option_ids = [row["id"] for row in single["options"]]
        invalid = self.client.post(
            f"/api/decisions/{single['id']}/vote/",
            {"family": str(self.family.id), "option_ids": option_ids},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400, invalid.data)
        self.assertEqual(invalid.data["code"], "invalid_vote_selection")

        multiple = self.create_decision(mode="multiple", options=["A", "B", "C"]).data
        selected = [row["id"] for row in multiple["options"][:2]]
        voted = self.client.post(
            f"/api/decisions/{multiple['id']}/vote/",
            {"family": str(self.family.id), "option_ids": selected},
            format="json",
        )
        self.assertEqual(voted.status_code, 200, voted.data)
        self.assertEqual(set(voted.data["my_option_ids"]), set(selected))
        self.assertEqual(sum(row["votes"] for row in voted.data["options"]), 2)

    def test_anonymous_results_never_expose_voter_identity(self):
        anonymous = self.create_decision(anonymous=True).data
        option_id = anonymous["options"][0]["id"]
        adult = self.client_for(self.adult)
        voted = adult.post(
            f"/api/decisions/{anonymous['id']}/vote/",
            {"family": str(self.family.id), "option_ids": [option_id]},
            format="json",
        )
        self.assertEqual(voted.status_code, 200, voted.data)
        self.assertEqual(voted.data["options"][0]["votes"], 1)
        self.assertNotIn("voters", voted.data["options"][0])
        detail = self.client.get(
            f"/api/decisions/{anonymous['id']}/?family={self.family.id}"
        )
        self.assertNotIn("voters", detail.data["options"][0])

        visible = self.create_decision(anonymous=False).data
        option_id = visible["options"][0]["id"]
        adult.post(
            f"/api/decisions/{visible['id']}/vote/",
            {"family": str(self.family.id), "option_ids": [option_id]},
            format="json",
        )
        detail = self.client.get(f"/api/decisions/{visible['id']}/?family={self.family.id}")
        self.assertEqual(detail.data["options"][0]["voters"][0]["membership"], str(self.adult_membership.id))
        self.assertEqual(detail.data["options"][0]["voters"][0]["name"], "Sam")

    def test_guest_is_read_only_and_cross_family_is_neutral(self):
        decision = self.create_decision().data
        guest = self.client_for(self.guest)
        listed = guest.get(f"/api/decisions/?family={self.family.id}")
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["count"], 1)
        vote = guest.post(
            f"/api/decisions/{decision['id']}/vote/",
            {"family": str(self.family.id), "option_ids": [decision["options"][0]["id"]]},
            format="json",
        )
        self.assertEqual(vote.status_code, 403, vote.data)
        create = guest.post(
            "/api/decisions/",
            {
                "family": str(self.family.id),
                "question": "Nope?",
                "options": ["A", "B"],
            },
            format="json",
        )
        self.assertEqual(create.status_code, 403, create.data)

        foreign = self.client_for(self.foreign)
        hidden = foreign.get(f"/api/decisions/{decision['id']}/?family={self.family.id}")
        self.assertEqual(hidden.status_code, 404, hidden.data)
        self.assertEqual(hidden.data["code"], "family_unavailable")

    def test_deadline_and_manual_close_block_future_votes(self):
        decision = self.create_decision().data
        row = Decision.objects.get(id=decision["id"])
        row.closes_at = timezone.now() - timedelta(seconds=1)
        row.save(update_fields=["closes_at", "updated_at"])
        expired = self.client.post(
            f"/api/decisions/{row.id}/vote/",
            {"family": str(self.family.id), "option_ids": [decision["options"][0]["id"]]},
            format="json",
        )
        self.assertEqual(expired.status_code, 409, expired.data)
        self.assertEqual(expired.data["code"], "decision_closed")

        open_decision = self.create_decision(question="Noch offen?").data
        closed = self.client.post(
            f"/api/decisions/{open_decision['id']}/close/",
            {"family": str(self.family.id)},
            format="json",
        )
        self.assertEqual(closed.status_code, 200, closed.data)
        self.assertFalse(closed.data["is_open"])
        blocked = self.client.post(
            f"/api/decisions/{open_decision['id']}/vote/",
            {"family": str(self.family.id), "option_ids": [open_decision["options"][0]["id"]]},
            format="json",
        )
        self.assertEqual(blocked.status_code, 409, blocked.data)

    def test_context_bound_note_follows_note_acl_without_leaking(self):
        note = Note.objects.create(family=self.family, author=self.owner, title="Private plan")
        created = self.create_decision(
            context={"type": "note", "id": str(note.id)},
        )
        self.assertEqual(created.status_code, 201, created.data)
        decision_id = created.data["id"]
        self.assertEqual(created.data["context"]["type"], "note")
        self.assertTrue(
            ContextLink.objects.filter(
                family=self.family,
                source_type="decision",
                source_id=decision_id,
                context_type="note",
                context_id=note.id,
                relation_key="decision.context",
            ).exists()
        )

        adult = self.client_for(self.adult)
        hidden = adult.get(f"/api/decisions/{decision_id}/?family={self.family.id}")
        self.assertEqual(hidden.status_code, 404, hidden.data)
        listed = adult.get(f"/api/decisions/?family={self.family.id}")
        self.assertEqual(listed.data["count"], 0)

        NoteShare.objects.create(note=note, user=self.adult, permission="read")
        visible = adult.get(f"/api/decisions/{decision_id}/?family={self.family.id}")
        self.assertEqual(visible.status_code, 200, visible.data)
        self.assertEqual(visible.data["context"]["id"], str(note.id))

        NoteShare.objects.filter(note=note, user=self.adult).delete()
        hidden_again = adult.get(f"/api/decisions/{decision_id}/?family={self.family.id}")
        self.assertEqual(hidden_again.status_code, 404, hidden_again.data)

    def test_context_rejects_foreign_targets_atomically_and_supports_events(self):
        foreign_task = Task.objects.create(
            family=self.other_family, title="Foreign", created_by=self.foreign
        )
        before = Decision.objects.count()
        denied = self.create_decision(
            question="Leak?",
            context={"type": "task", "id": str(foreign_task.id)},
        )
        self.assertEqual(denied.status_code, 404, denied.data)
        self.assertEqual(Decision.objects.count(), before)

        event = FamilyEvent.objects.create(
            family=self.family,
            type="manual",
            title="Familienabend",
            starts_at=timezone.now() + timedelta(days=1),
        )
        linked = self.create_decision(
            question="Was essen wir?",
            context={"type": "event", "id": str(event.id)},
        )
        self.assertEqual(linked.status_code, 201, linked.data)
        self.assertEqual(linked.data["context"]["type"], "event")
        self.assertIn(str(event.id), linked.data["context"]["deep_link"])
