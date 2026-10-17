from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Family, Membership, Routine, RoutineLog, RoutineReminderState, Task
from .routine_task_migration_models import RoutineTaskMigration
from .unified_action_models import ActionCompletion


class RoutineTaskMigrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="routine-migrator")
        self.other = get_user_model().objects.create_user(username="routine-other")
        self.family = Family.objects.create(name="Migration Family", slug="routine-migration")
        self.membership = Membership.objects.create(user=self.user, family=self.family, role="owner")
        self.other_membership = Membership.objects.create(user=self.other, family=self.family, role="adult")
        self.routine = Routine.objects.create(
            family=self.family,
            name="Pflanzen gießen",
            icon="droplets",
            active=True,
            target_count=3,
            target_period_days=10,
            reminder_enabled=True,
            suggested_interval_days=4,
        )
        self.first_log = RoutineLog.objects.create(
            routine=self.routine,
            done_by=self.other,
            done_at=timezone.now() - timedelta(days=3),
            note="Große Pflanzen mitgedacht",
            request_id=uuid4(),
        )
        RoutineReminderState.objects.create(
            routine=self.routine,
            membership=self.membership,
            snoozed_until=timezone.now() + timedelta(hours=8),
            last_sent_at=timezone.now() - timedelta(hours=2),
            last_cycle_at=timezone.now() - timedelta(days=1),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.path = f"/api/routine-migrations/{self.routine.id}/"

    def test_editor_status_starts_unmigrated(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["migrated"])

    def test_migration_preserves_properties_history_and_is_idempotent(self):
        first = self.client.post(self.path, {}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        task_id = first.data["task_id"]
        second = self.client.post(self.path, {}, format="json")
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data["task_id"], task_id)
        self.assertFalse(second.data["created"])

        self.assertEqual(Task.objects.filter(source=f"routine-migration:{self.routine.id}").count(), 1)
        migration = RoutineTaskMigration.objects.select_related("task").get(routine=self.routine)
        self.assertEqual(str(migration.task_id), task_id)
        snapshot = migration.snapshot
        self.assertEqual(snapshot["routine"]["name"], "Pflanzen gießen")
        self.assertEqual(snapshot["routine"]["icon"], "droplets")
        self.assertEqual(snapshot["routine"]["target_count"], 3)
        self.assertEqual(snapshot["routine"]["target_period_days"], 10)
        self.assertTrue(snapshot["routine"]["reminder_enabled"])
        self.assertEqual(snapshot["logs"][0]["note"], "Große Pflanzen mitgedacht")
        self.assertEqual(len(snapshot["reminder_states"]), 1)
        completion = ActionCompletion.objects.get(legacy_log=self.first_log)
        self.assertEqual(completion.action.legacy_task_id, migration.task_id)
        self.assertEqual(completion.actor_id, self.other.id)

    def test_current_editor_values_are_applied_before_migration(self):
        response = self.client.post(
            self.path,
            {
                "routine": {
                    "family": str(self.family.id),
                    "name": "Pflanzen & Kräuter",
                    "icon": "sparkles",
                    "active": False,
                    "target_count": 5,
                    "target_period_days": 12,
                    "reminder_enabled": False,
                }
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        migration = RoutineTaskMigration.objects.select_related("task").get(routine=self.routine)
        self.assertEqual(migration.task.title, "Pflanzen & Kräuter")
        self.assertEqual(migration.snapshot["routine"]["target_count"], 5)
        self.assertEqual(migration.snapshot["routine"]["target_period_days"], 12)
        self.assertFalse(migration.snapshot["routine"]["active"])
        self.assertFalse(migration.snapshot["routine"]["reminder_enabled"])
        self.assertEqual(migration.task.unified_action.state, "paused")

    def test_new_task_remains_recurring_and_updates_legacy_learning_history(self):
        migrated = self.client.post(self.path, {}, format="json")
        task_id = migrated.data["task_id"]
        action_path = "/api/actions/execute/"
        first = self.client.post(
            action_path,
            {"action_id": f"task:{task_id}", "request_id": str(uuid4())},
            format="json",
        )
        second = self.client.post(
            action_path,
            {"action_id": f"task:{task_id}", "request_id": str(uuid4())},
            format="json",
        )
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertNotEqual(first.data["id"], second.data["id"])
        self.assertEqual(self.routine.logs.count(), 3)
        migration = RoutineTaskMigration.objects.get(routine=self.routine)
        self.assertEqual(
            ActionCompletion.objects.filter(action__legacy_task_id=migration.task_id, undone_at__isnull=True).count(),
            3,
        )

        undo = self.client.post(
            action_path,
            {
                "action_id": f"task:{task_id}",
                "operation": "undo",
                "completion_id": second.data["id"],
                "request_id": str(uuid4()),
            },
            format="json",
        )
        self.assertEqual(undo.status_code, 200, undo.data)
        self.assertEqual(self.routine.logs.count(), 2)

    def test_action_feed_replaces_legacy_routine_with_migrated_task(self):
        migrated = self.client.post(self.path, {}, format="json")
        task_id = migrated.data["task_id"]
        response = self.client.get(f"/api/actions/?family={self.family.id}&scope=all")
        self.assertEqual(response.status_code, 200, response.data)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(f"task:{task_id}", ids)
        self.assertNotIn(f"routine:{self.routine.id}", ids)
        task_row = next(row for row in response.data["results"] if row["id"] == f"task:{task_id}")
        self.assertEqual(task_row["migration"]["from"], "routine")
        self.assertEqual(task_row["repeat"]["target_count"], 3)
        self.assertEqual(task_row["repeat"]["target_period_days"], 10)

    def test_family_boundary_is_enforced(self):
        outsider = get_user_model().objects.create_user(username="routine-outsider")
        self.client.force_authenticate(outsider)
        response = self.client.post(self.path, {}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(RoutineTaskMigration.objects.exists())
