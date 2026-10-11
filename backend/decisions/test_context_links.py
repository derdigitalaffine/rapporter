from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from family.models import Family, Membership
from family.notes_models import Note, NoteShare


class DecisionContextLinkApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="decision-link-owner")
        self.reader = User.objects.create_user(username="decision-link-reader")
        self.family = Family.objects.create(name="Decision Links", slug="decision-links")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family, user=self.reader, role=Membership.Role.ADULT)
        self.note = Note.objects.create(family=self.family, author=self.owner, title="Private context")
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner)
        self.reader_client = APIClient()
        self.reader_client.force_authenticate(self.reader)

    def test_generic_context_link_api_tracks_note_acl_for_decision(self):
        created = self.owner_client.post(
            "/api/decisions/",
            {
                "family": str(self.family.id),
                "question": "Was nehmen wir mit?",
                "options": ["A", "B"],
                "context": {"type": "note", "id": str(self.note.id)},
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)
        decision_id = created.data["id"]

        hidden = self.reader_client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "note",
                "anchor_id": str(self.note.id),
            },
        )
        # The reader cannot resolve the private Note anchor yet, so the generic
        # ContextLink endpoint must not reveal whether a linked decision exists.
        self.assertEqual(hidden.status_code, 404, hidden.data)

        NoteShare.objects.create(note=self.note, user=self.reader, permission="read")
        visible = self.reader_client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "note",
                "anchor_id": str(self.note.id),
            },
        )
        self.assertEqual(visible.status_code, 200, visible.data)
        self.assertEqual(visible.data["count"], 1)
        link = visible.data["results"][0]
        self.assertEqual(link["source"]["type"], "decision")
        self.assertEqual(link["source"]["id"], decision_id)
        self.assertEqual(link["context"]["type"], "note")

        NoteShare.objects.filter(note=self.note, user=self.reader).delete()
        hidden_again = self.reader_client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "decision",
                "anchor_id": decision_id,
            },
        )
        self.assertEqual(hidden_again.status_code, 404, hidden_again.data)
