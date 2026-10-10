from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .context_models import ContextLink
from .models import Family, Membership, Task
from .notes_models import Note, NoteShare
from .travel_models import Trip


class ContextLinkApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="context-owner")
        self.viewer = User.objects.create_user(username="context-viewer")
        self.guest = User.objects.create_user(username="context-guest")
        self.foreign_user = User.objects.create_user(username="context-foreign")

        self.family = Family.objects.create(name="Context Family", slug="context-family")
        self.foreign_family = Family.objects.create(name="Foreign Family", slug="context-foreign-family")
        Membership.objects.create(family=self.family, user=self.owner, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.family, user=self.viewer, role=Membership.Role.TEEN)
        Membership.objects.create(family=self.family, user=self.guest, role=Membership.Role.GUEST)
        Membership.objects.create(
            family=self.foreign_family,
            user=self.foreign_user,
            role=Membership.Role.OWNER,
        )

        self.task = Task.objects.create(family=self.family, title="Pack bags", created_by=self.owner)
        self.trip = Trip.objects.create(
            family=self.family,
            title="Japan",
            starts_on="2027-03-01",
            ends_on="2027-03-08",
            created_by=self.owner,
        )
        self.foreign_task = Task.objects.create(
            family=self.foreign_family,
            title="Foreign secret",
            created_by=self.foreign_user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def payload(self, **overrides):
        values = {
            "family": str(self.family.id),
            "source": {"type": "task", "id": str(self.task.id)},
            "context": {"type": "trip", "id": str(self.trip.id)},
            "relation": "context",
        }
        values.update(overrides)
        return values

    def create_link(self, client=None, **overrides):
        return (client or self.client).post("/api/context-links/", self.payload(**overrides), format="json")

    def test_create_is_idempotent_and_list_returns_canonical_metadata(self):
        first = self.create_link()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertTrue(first.data["created"])
        self.assertEqual(first.data["link"]["source"]["type"], "task")
        self.assertEqual(first.data["link"]["source"]["id"], str(self.task.id))
        self.assertEqual(first.data["link"]["source"]["deep_link"], f"/?page=tasks&task={self.task.id}")
        self.assertEqual(first.data["link"]["context"]["lifecycle"], "available")

        second = self.create_link()
        self.assertEqual(second.status_code, 200, second.data)
        self.assertFalse(second.data["created"])
        self.assertEqual(second.data["link"]["id"], first.data["link"]["id"])
        self.assertEqual(ContextLink.objects.count(), 1)

        listed = self.client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "trip",
                "anchor_id": str(self.trip.id),
            },
        )
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["id"], first.data["link"]["id"])
        self.assertEqual(listed.data["results"][0]["context"]["deep_link"], "/?page=trips")

    def test_cross_family_family_and_target_are_neutral_unavailable(self):
        foreign_family = self.create_link(family=str(self.foreign_family.id))
        foreign_target = self.create_link(
            source={"type": "task", "id": str(self.foreign_task.id)}
        )
        self.assertEqual(foreign_family.status_code, 404, foreign_family.data)
        self.assertEqual(foreign_target.status_code, 404, foreign_target.data)
        self.assertEqual(foreign_family.data, foreign_target.data)
        self.assertEqual(foreign_family.data["code"], "context_object_unavailable")
        self.assertFalse(ContextLink.objects.exists())

    def test_read_only_note_share_can_list_but_cannot_create_or_delete(self):
        note = Note.objects.create(family=self.family, author=self.owner, title="Shared plan")
        share = NoteShare.objects.create(note=note, user=self.viewer, permission="read")
        created = self.create_link(source={"type": "note", "id": str(note.id)})
        self.assertEqual(created.status_code, 201, created.data)
        link_id = created.data["link"]["id"]

        viewer_client = APIClient()
        viewer_client.force_authenticate(self.viewer)
        listed = viewer_client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "trip",
                "anchor_id": str(self.trip.id),
            },
        )
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["count"], 1)

        denied_create = self.create_link(
            client=viewer_client,
            source={"type": "note", "id": str(note.id)},
        )
        self.assertEqual(denied_create.status_code, 403, denied_create.data)
        self.assertEqual(denied_create.data["code"], "context_link_forbidden")

        denied_delete = viewer_client.delete(
            f"/api/context-links/{link_id}/?family={self.family.id}"
        )
        self.assertEqual(denied_delete.status_code, 403, denied_delete.data)
        self.assertTrue(ContextLink.objects.filter(id=link_id).exists())

        share.delete()
        hidden = viewer_client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "trip",
                "anchor_id": str(self.trip.id),
            },
        )
        self.assertEqual(hidden.status_code, 200, hidden.data)
        self.assertEqual(hidden.data["count"], 0)
        self.assertEqual(hidden.data["results"], [])

    def test_guest_can_read_visible_link_but_cannot_mutate(self):
        created = self.create_link()
        self.assertEqual(created.status_code, 201, created.data)
        link_id = created.data["link"]["id"]

        guest_client = APIClient()
        guest_client.force_authenticate(self.guest)
        listed = guest_client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "trip",
                "anchor_id": str(self.trip.id),
            },
        )
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertEqual(listed.data["count"], 1)

        denied_create = self.create_link(client=guest_client)
        self.assertEqual(denied_create.status_code, 403, denied_create.data)
        denied_delete = guest_client.delete(
            f"/api/context-links/{link_id}/?family={self.family.id}"
        )
        self.assertEqual(denied_delete.status_code, 403, denied_delete.data)
        self.assertTrue(ContextLink.objects.filter(id=link_id).exists())

    def test_delete_removes_only_link_metadata(self):
        created = self.create_link()
        link_id = created.data["link"]["id"]
        deleted = self.client.delete(
            f"/api/context-links/{link_id}/?family={self.family.id}"
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(ContextLink.objects.filter(id=link_id).exists())
        self.assertTrue(Task.objects.filter(id=self.task.id).exists())
        self.assertTrue(Trip.objects.filter(id=self.trip.id).exists())

    def test_allowlist_and_limit_validation_use_stable_error_codes(self):
        bad_type = self.create_link(
            source={"type": "arbitrary_model", "id": str(self.task.id)}
        )
        self.assertEqual(bad_type.status_code, 400, bad_type.data)
        self.assertEqual(bad_type.data["code"], "unsupported_context_type")

        bad_relation = self.create_link(relation="owner")
        self.assertEqual(bad_relation.status_code, 400, bad_relation.data)
        self.assertEqual(bad_relation.data["code"], "unsupported_context_relation")

        bad_limit = self.client.get(
            "/api/context-links/",
            {
                "family": str(self.family.id),
                "anchor_type": "trip",
                "anchor_id": str(self.trip.id),
                "limit": "0",
            },
        )
        self.assertEqual(bad_limit.status_code, 400, bad_limit.data)
        self.assertEqual(bad_limit.data["code"], "invalid_limit")
