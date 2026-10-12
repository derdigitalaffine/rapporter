import io
import json
import uuid
from importlib import import_module

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from .board_migration import IDENTITY_STRATEGY, migration_report, repair_legacy_adapter_keys
from .models import BoardImage, BoardPost, Family, Membership, Task


class PinboardMigrationCompatibilityTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("pin-migration-user")
        self.outsider = User.objects.create_user("pin-migration-outsider")
        self.family = Family.objects.create(name="Migration family", slug="migration-family")
        self.other = Family.objects.create(name="Other migration family", slug="other-migration-family")
        self.membership = Membership.objects.create(
            family=self.family,
            user=self.user,
            role=Membership.Role.OWNER,
        )
        self.other_membership = Membership.objects.create(
            family=self.other,
            user=self.outsider,
            role=Membership.Role.OWNER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_repair_is_bounded_idempotent_and_preserves_pin_identity(self):
        task = Task.objects.create(family=self.family, title="Legacy task", created_by=self.user)
        legacy = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.TASK,
            target_id=task.id,
            adapter_key="",
        )
        canonical = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.TASK,
            target_id=task.id,
            adapter_key="task",
        )
        native = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.NOTE,
            text="Native note",
        )
        original_ids = {legacy.id, canonical.id, native.id}

        self.assertEqual(repair_legacy_adapter_keys(batch_size=1), 1)
        self.assertEqual(repair_legacy_adapter_keys(batch_size=1), 0)

        legacy.refresh_from_db()
        self.assertEqual(legacy.adapter_key, "task")
        self.assertEqual(legacy.kind, BoardPost.Kind.TASK)
        self.assertEqual(legacy.target_id, task.id)
        self.assertEqual(set(BoardPost.objects.values_list("id", flat=True)), original_ids)

    def test_report_is_count_only_and_flags_orphans_and_visibility_anomalies(self):
        task = Task.objects.create(family=self.family, title="SECRET TARGET", created_by=self.user)
        BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.TASK,
            target_id=task.id,
            adapter_key="",
        )
        BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.TASK,
            target_id=uuid.uuid4(),
            adapter_key="task",
        )
        secret = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.NOTE,
            text="NEVER-LOG-THIS-PRIVATE-TEXT",
        )
        BoardImage.objects.create(
            post=secret,
            key="never-log-this-private-media-key",
            width=20,
            height=10,
        )
        selected_without_people = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.NOTE,
            text="selected",
            visibility=BoardPost.Visibility.SELECTED,
        )
        cross_family = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.NOTE,
            text="cross family",
            visibility=BoardPost.Visibility.SELECTED,
        )
        cross_family.visible_to_memberships.add(self.other_membership)
        stale_grant = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.NOTE,
            text="stale grant",
            visibility=BoardPost.Visibility.FAMILY,
        )
        stale_grant.visible_to_memberships.add(self.membership)

        report = migration_report()
        self.assertEqual(report["identity_strategy"], IDENTITY_STRATEGY)
        self.assertEqual(report["identity_compatible"], report["board_posts_total"])
        self.assertEqual(report["adapter_backfill_needed"], 1)
        self.assertEqual(report["orphaned_targets"], 1)
        self.assertEqual(report["orphaned_images"], 0)
        self.assertEqual(report["visibility_anomalies"], 3)
        self.assertEqual(report["errors"], 0)
        self.assertNotIn("NEVER-LOG", json.dumps(report))
        self.assertIsNotNone(selected_without_people.id)

        output = io.StringIO()
        call_command("report_pinboard_migration", "--json", stdout=output)
        command_output = output.getvalue()
        self.assertNotIn("NEVER-LOG", command_output)
        self.assertNotIn("SECRET TARGET", command_output)
        self.assertNotIn("never-log-this-private-media-key", command_output)
        decoded = json.loads(command_output)
        self.assertEqual(decoded["orphaned_targets"], 1)

    def test_command_repair_reports_new_and_already_migrated_rows_without_duplicates(self):
        task = Task.objects.create(family=self.family, title="Task", created_by=self.user)
        legacy = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.TASK,
            target_id=task.id,
            adapter_key="",
        )
        native = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.NOTE,
            text="Note",
        )

        first = io.StringIO()
        call_command(
            "report_pinboard_migration",
            "--repair-adapter-keys",
            "--batch-size=1",
            "--json",
            stdout=first,
        )
        first_report = json.loads(first.getvalue())
        self.assertEqual(first_report["migrated"], 1)
        self.assertEqual(first_report["already_migrated"], 1)
        self.assertEqual(first_report["adapter_backfill_needed"], 0)
        self.assertEqual(BoardPost.objects.count(), 2)

        second = io.StringIO()
        call_command(
            "report_pinboard_migration",
            "--repair-adapter-keys",
            "--batch-size=1",
            "--json",
            stdout=second,
        )
        second_report = json.loads(second.getvalue())
        self.assertEqual(second_report["migrated"], 0)
        self.assertEqual(second_report["already_migrated"], 2)
        self.assertEqual(BoardPost.objects.count(), 2)
        legacy.refresh_from_db()
        self.assertEqual(legacy.adapter_key, "task")
        self.assertTrue(BoardPost.objects.filter(pk=native.pk).exists())

    def test_boardpost_uuid_remains_the_authorized_deep_link_identity(self):
        post = BoardPost.objects.create(
            family=self.family,
            author=self.user,
            kind=BoardPost.Kind.NOTE,
            text="Stable deep link",
        )

        response = self.client.get(f"/api/board/{post.id}/?family={self.family.id}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["id"], str(post.id))

        self.client.force_authenticate(self.outsider)
        response = self.client.get(f"/api/board/{post.id}/?family={self.family.id}")
        self.assertEqual(response.status_code, 404)


class PinboardLegacyUpgradeRollbackTests(TransactionTestCase):
    migrate_from = [("family", "0202_board")]
    migrate_to = [("family", "0224_merge_create_preferences_pin_visibility")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        FamilyModel = old_apps.get_model("family", "Family")
        BoardPostModel = old_apps.get_model("family", "BoardPost")
        BoardImageModel = old_apps.get_model("family", "BoardImage")

        family = FamilyModel.objects.create(name="Legacy board", slug="legacy-board")
        note = BoardPostModel.objects.create(family=family, text="Legacy text stays exact")
        photo = BoardPostModel.objects.create(family=family, text="Legacy photo caption")
        image = BoardImageModel.objects.create(
            post=photo,
            key="0123456789abcdef0123456789abcdef",
            width=640,
            height=480,
        )
        self.family_id = family.id
        self.note_id = note.id
        self.photo_id = photo.id
        self.image_id = image.id

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.upgraded_apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_upgrade_and_rollback_preserve_boardpost_and_image_identity(self):
        BoardPostModel = self.upgraded_apps.get_model("family", "BoardPost")
        BoardImageModel = self.upgraded_apps.get_model("family", "BoardImage")

        note = BoardPostModel.objects.get(pk=self.note_id)
        photo = BoardPostModel.objects.get(pk=self.photo_id)
        image = BoardImageModel.objects.get(pk=self.image_id)
        self.assertEqual(note.id, self.note_id)
        self.assertEqual(note.text, "Legacy text stays exact")
        self.assertEqual(note.kind, "note")
        self.assertEqual(note.visibility, "family")
        self.assertEqual(photo.id, self.photo_id)
        self.assertEqual(photo.kind, "photo")
        self.assertEqual(photo.text, "Legacy photo caption")
        self.assertEqual(image.post_id, self.photo_id)
        self.assertEqual(image.key, "0123456789abcdef0123456789abcdef")
        self.assertEqual((image.width, image.height), (640, 480))

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        rolled_back_apps = executor.loader.project_state(self.migrate_from).apps
        LegacyPost = rolled_back_apps.get_model("family", "BoardPost")
        LegacyImage = rolled_back_apps.get_model("family", "BoardImage")

        rolled_note = LegacyPost.objects.get(pk=self.note_id)
        rolled_photo = LegacyPost.objects.get(pk=self.photo_id)
        rolled_image = LegacyImage.objects.get(pk=self.image_id)
        self.assertEqual(rolled_note.id, self.note_id)
        self.assertEqual(rolled_note.text, "Legacy text stays exact")
        self.assertEqual(rolled_photo.id, self.photo_id)
        self.assertEqual(rolled_photo.text, "Legacy photo caption")
        self.assertEqual(rolled_image.post_id, self.photo_id)
        self.assertEqual(rolled_image.key, "0123456789abcdef0123456789abcdef")
