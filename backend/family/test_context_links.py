from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .board_models import BoardPost
from .context_links import (
    ContextLinkPermissionDenied,
    ContextObjectUnavailable,
    UnsupportedContextRelation,
    UnsupportedContextType,
    create_context_link,
    list_context_links,
    remove_context_link,
)
from .context_models import ContextLink
from .models import Family, Membership, Task
from .notes_models import Note, NoteShare
from .travel_models import Trip


class ContextLinkServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice")
        self.viewer = User.objects.create_user(username="viewer")
        self.guest = User.objects.create_user(username="guest")
        self.other = User.objects.create_user(username="other")
        self.family = Family.objects.create(name="A", slug="a")
        self.other_family = Family.objects.create(name="B", slug="b")
        Membership.objects.create(family=self.family, user=self.alice, role=Membership.Role.ADULT)
        Membership.objects.create(family=self.family, user=self.viewer, role=Membership.Role.TEEN)
        Membership.objects.create(family=self.family, user=self.guest, role=Membership.Role.GUEST)
        Membership.objects.create(family=self.other_family, user=self.other, role=Membership.Role.ADULT)
        self.trip = Trip.objects.create(
            family=self.family,
            title="Japan",
            starts_on="2027-03-01",
            ends_on="2027-03-08",
            created_by=self.alice,
        )
        self.task = Task.objects.create(family=self.family, title="Packen", created_by=self.alice)

    def link(self, **overrides):
        values = {
            "user": self.alice,
            "family": self.family,
            "source_type": "task",
            "source_id": self.task.id,
            "context_type": "trip",
            "context_id": self.trip.id,
        }
        values.update(overrides)
        return create_context_link(**values)

    def test_create_is_idempotent_and_keeps_canonical_objects(self):
        first, created = self.link()
        second, created_again = self.link()
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, second.id)
        self.assertEqual(ContextLink.objects.count(), 1)
        self.assertTrue(Task.objects.filter(pk=self.task.id).exists())
        self.assertTrue(Trip.objects.filter(pk=self.trip.id).exists())

    def test_cross_family_target_is_neutral_unavailable(self):
        foreign_task = Task.objects.create(family=self.other_family, title="Secret", created_by=self.other)
        with self.assertRaises(ContextObjectUnavailable):
            self.link(source_id=foreign_task.id)
        self.assertFalse(ContextLink.objects.exists())

    def test_hidden_task_and_unshared_note_cannot_be_linked(self):
        hidden = Task.objects.create(
            family=self.family,
            title="Gift",
            created_by=self.alice,
            hidden_from_user=self.viewer,
        )
        with self.assertRaises(ContextObjectUnavailable):
            self.link(user=self.viewer, source_id=hidden.id)

        note = Note.objects.create(family=self.family, author=self.alice, title="Private")
        with self.assertRaises(ContextObjectUnavailable):
            self.link(user=self.viewer, source_type="note", source_id=note.id)

    def test_read_only_note_share_can_view_but_cannot_mutate_links(self):
        note = Note.objects.create(family=self.family, author=self.alice, title="Shared")
        share = NoteShare.objects.create(note=note, user=self.viewer, permission="read")
        link, _ = self.link(source_type="note", source_id=note.id)

        rows = list_context_links(
            user=self.viewer,
            family=self.family,
            anchor_type="trip",
            anchor_id=self.trip.id,
        )
        self.assertEqual([row.link.id for row in rows], [link.id])
        with self.assertRaises(ContextLinkPermissionDenied):
            self.link(user=self.viewer, source_type="note", source_id=note.id)
        with self.assertRaises(ContextLinkPermissionDenied):
            remove_context_link(user=self.viewer, family=self.family, link_id=link.id)

        share.permission = "edit"
        share.save(update_fields=["permission"])
        same_link, created = self.link(user=self.viewer, source_type="note", source_id=note.id)
        self.assertFalse(created)
        self.assertEqual(same_link.id, link.id)
        remove_context_link(user=self.viewer, family=self.family, link_id=link.id)
        self.assertFalse(ContextLink.objects.filter(pk=link.id).exists())

    def test_note_share_revocation_hides_existing_link_without_snapshot_leak(self):
        note = Note.objects.create(family=self.family, author=self.alice, title="Visible once")
        NoteShare.objects.create(note=note, user=self.viewer, permission="read")
        link, _ = self.link(source_type="note", source_id=note.id)
        self.assertEqual(
            len(
                list_context_links(
                    user=self.viewer,
                    family=self.family,
                    anchor_type="trip",
                    anchor_id=self.trip.id,
                )
            ),
            1,
        )

        note.shares.filter(user=self.viewer).delete()
        self.assertEqual(
            list_context_links(
                user=self.viewer,
                family=self.family,
                anchor_type="trip",
                anchor_id=self.trip.id,
            ),
            [],
        )
        self.assertTrue(ContextLink.objects.filter(pk=link.id).exists())

    def test_guest_and_non_member_cannot_create(self):
        with self.assertRaises(ContextLinkPermissionDenied):
            self.link(user=self.guest)
        with self.assertRaises(ContextLinkPermissionDenied):
            self.link(user=self.other)

    def test_unknown_type_and_relation_are_rejected_by_allowlist(self):
        with self.assertRaises(UnsupportedContextType):
            self.link(source_type="arbitrary_model")
        with self.assertRaises(UnsupportedContextRelation):
            self.link(relation_key="owner")
        with self.assertRaises(UnsupportedContextRelation):
            self.link(
                source_type="trip",
                source_id=self.trip.id,
                context_type="task",
                context_id=self.task.id,
            )

    def test_deleted_target_becomes_unavailable_and_archived_lifecycle_is_explicit(self):
        self.link()
        self.trip.archived = True
        self.trip.save(update_fields=["archived", "updated_at"])
        rows = list_context_links(
            user=self.alice,
            family=self.family,
            anchor_type="trip",
            anchor_id=self.trip.id,
        )
        self.assertEqual(rows[0].context.lifecycle, "archived")

        task_id = self.task.id
        self.task.delete()
        self.assertEqual(
            list_context_links(
                user=self.alice,
                family=self.family,
                anchor_type="trip",
                anchor_id=self.trip.id,
            ),
            [],
        )
        self.assertTrue(ContextLink.objects.filter(source_id=task_id).exists())

    def test_remove_link_never_deletes_either_endpoint_and_can_clean_stale_context(self):
        link, _ = self.link()
        remove_context_link(user=self.alice, family=self.family, link_id=link.id)
        self.assertFalse(ContextLink.objects.filter(pk=link.id).exists())
        self.assertTrue(Task.objects.filter(pk=self.task.id).exists())
        self.assertTrue(Trip.objects.filter(pk=self.trip.id).exists())

        link, _ = self.link()
        self.trip.delete()
        remove_context_link(user=self.alice, family=self.family, link_id=link.id)
        self.assertFalse(ContextLink.objects.filter(pk=link.id).exists())

    def test_remove_invalid_id_is_neutral_unavailable(self):
        with self.assertRaises(ContextObjectUnavailable):
            remove_context_link(user=self.alice, family=self.family, link_id="not-a-uuid")

    def test_task_note_and_pinboard_refs_resolve_with_existing_deep_links(self):
        note = Note.objects.create(family=self.family, author=self.alice, title="Plan")
        board = BoardPost.objects.create(family=self.family, author=self.alice, text="Board")
        self.link(source_type="note", source_id=note.id)
        self.link(source_type="board_post", source_id=board.id)
        rows = list_context_links(
            user=self.alice,
            family=self.family,
            anchor_type="trip",
            anchor_id=self.trip.id,
        )
        self.assertEqual({row.source.ref.type for row in rows}, {"note", "board_post"})
        links = {row.source.ref.type: row.source.deep_link for row in rows}
        self.assertEqual(links["note"], f"/?page=notes&note={note.id}")
        self.assertEqual(links["board_post"], f"/?page=board&post={board.id}&family={self.family.id}")

    def test_listing_batches_same_type_without_n_plus_one(self):
        for index in range(20):
            task = Task.objects.create(family=self.family, title=f"Task {index}", created_by=self.alice)
            self.link(source_id=task.id)
        with CaptureQueriesContext(connection) as queries:
            rows = list_context_links(
                user=self.alice,
                family=self.family,
                anchor_type="trip",
                anchor_id=self.trip.id,
                limit=50,
            )
        self.assertEqual(len(rows), 20)
        self.assertEqual(len(queries), 4)
