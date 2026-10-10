from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from .action_projection import ActionProjectionError, MAX_ROUTINE_LOGS, parse_action_id, project_actions
from .models import Family, Membership, Routine, RoutineLog, Task, TaskList, TaskWorkflowColumn


UTC = dt_timezone.utc


class ActionProjectionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice-actions", password="test-pass-123")
        self.bob = User.objects.create_user(username="bob-actions", password="test-pass-123")
        self.family = Family.objects.create(name="Actions Family", slug="actions-family", timezone="Europe/Berlin")
        self.other = Family.objects.create(name="Other Actions", slug="other-actions", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.alice, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other, user=self.bob, role=Membership.Role.OWNER)
        self.task_list = TaskList.objects.create(family=self.family, name="Allgemein")
        self.workflow_list = TaskList.objects.create(family=self.family, name="Workflow", workflow_enabled=True)
        self.open_column = TaskWorkflowColumn.objects.create(task_list=self.workflow_list, name="Offen", key="open", position=0, kind="open")
        self.active_column = TaskWorkflowColumn.objects.create(task_list=self.workflow_list, name="In Arbeit", key="active", position=10, kind="active")
        self.done_column = TaskWorkflowColumn.objects.create(task_list=self.workflow_list, name="Erledigt", key="done", position=20, kind="done", is_terminal=True)
        self.other_list = TaskList.objects.create(family=self.other, name="Privat")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)
        self.now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)

    def rows(self, response):
        return response.data.get("results", response.data)

    def task(self, title, **kwargs):
        defaults = {"family": self.family, "task_list": self.task_list, "created_by": self.alice, "title": title}
        defaults.update(kwargs)
        return Task.objects.create(**defaults)

    def test_one_feed_contains_typed_task_and_routine_without_cross_family_rows(self):
        task = self.task("Heute", due_at=self.now)
        routine = Routine.objects.create(family=self.family, name="Lüften", target_count=1, target_period_days=1)
        Routine.objects.filter(pk=routine.pk).update(created_at=self.now - timedelta(days=2))
        foreign_task = Task.objects.create(family=self.other, task_list=self.other_list, created_by=self.bob, title="Fremd", due_at=self.now)
        foreign_routine = Routine.objects.create(family=self.other, name="Fremde Routine", target_count=1, target_period_days=1)

        with patch("family.action_projection.timezone.now", return_value=self.now):
            response = self.client.get(f"/api/actions/?family={self.family.id}&scope=today")

        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in self.rows(response)}
        self.assertIn(f"task:{task.id}", ids)
        self.assertIn(f"routine:{routine.id}", ids)
        self.assertNotIn(f"task:{foreign_task.id}", ids)
        self.assertNotIn(f"routine:{foreign_routine.id}", ids)
        self.assertEqual(response.data["ranking_version"], "actions-v1")

    def test_foreign_family_is_rejected_without_data_leak(self):
        Task.objects.create(family=self.other, task_list=self.other_list, created_by=self.bob, title="Geheim", due_at=self.now)
        response = self.client.get(f"/api/actions/?family={self.other.id}&scope=all")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Geheim", str(response.data))

    def test_task_projection_preserves_workflow_assignee_priority_and_recurrence(self):
        task = self.task(
            "Wiederkehrend",
            task_list=self.workflow_list,
            workflow_column=self.active_column,
            assignee=self.alice,
            priority=Task.Priority.HIGH,
            recurrence="weekly",
            due_at=self.now + timedelta(days=2),
        )

        rows = project_actions(user=self.alice, family=self.family, scope="all", kind="tasks", now=self.now)
        row = next(item for item in rows if item["id"] == f"task:{task.id}")

        self.assertEqual(row["kind"], "task")
        self.assertEqual(row["state"], "active")
        self.assertEqual(row["assignee"]["id"], self.alice.id)
        self.assertEqual(row["priority"], "high")
        self.assertEqual(row["repeat"], {"recurrence": "weekly"})
        self.assertEqual(row["context"]["list"]["id"], str(self.workflow_list.id))
        self.assertEqual(row["context"]["workflow"]["kind"], "active")
        self.assertEqual(row["primary_action"]["href"], f"/api/tasks/{task.id}/toggle/")

    def test_typed_ids_cannot_be_reinterpreted_across_domains(self):
        task = self.task("Collision", due_at=self.now)
        routine = Routine.objects.create(id=task.id, family=self.family, name="Same UUID", target_count=1, target_period_days=1)
        Routine.objects.filter(pk=routine.pk).update(created_at=self.now - timedelta(days=2))

        rows = project_actions(user=self.alice, family=self.family, scope="today", now=self.now)
        ids = {row["id"] for row in rows}
        self.assertIn(f"task:{task.id}", ids)
        self.assertIn(f"routine:{task.id}", ids)
        self.assertEqual(parse_action_id(f"task:{task.id}", expected_kind="task")[0], "task")
        with self.assertRaises(ActionProjectionError):
            parse_action_id(f"task:{task.id}", expected_kind="routine")

    def test_paused_routine_is_hidden_from_today_but_visible_in_routine_filter(self):
        routine = Routine.objects.create(family=self.family, name="Pause", active=False, target_count=1, target_period_days=1)
        Routine.objects.filter(pk=routine.pk).update(created_at=self.now - timedelta(days=5))

        today = project_actions(user=self.alice, family=self.family, scope="today", now=self.now)
        routines = project_actions(user=self.alice, family=self.family, scope="routines", now=self.now)

        self.assertNotIn(f"routine:{routine.id}", {row["id"] for row in today})
        row = next(row for row in routines if row["id"] == f"routine:{routine.id}")
        self.assertEqual(row["state"], "paused")
        self.assertEqual(row["primary_action"]["id"], "reactivate")

    def test_list_and_mine_filters_do_not_pull_unrelated_routines(self):
        mine = self.task("Mein Task", assignee=self.alice)
        self.task("Unassigned")
        Routine.objects.create(family=self.family, name="Routine", target_count=1, target_period_days=7)

        list_rows = project_actions(user=self.alice, family=self.family, scope="all", list_id=self.task_list.id, now=self.now)
        mine_rows = project_actions(user=self.alice, family=self.family, scope="mine", now=self.now)

        self.assertTrue(list_rows)
        self.assertEqual({row["kind"] for row in list_rows}, {"task"})
        self.assertEqual([row["id"] for row in mine_rows], [f"task:{mine.id}"])

    def test_ranking_is_deterministic_and_purely_presentational(self):
        overdue = self.task("Overdue", due_at=self.now - timedelta(days=1))
        due = self.task("Due", due_at=self.now)
        active = self.task("Active", task_list=self.workflow_list, workflow_column=self.active_column, due_at=None)

        first = project_actions(user=self.alice, family=self.family, scope="today", kind="tasks", now=self.now)
        second = project_actions(user=self.alice, family=self.family, scope="today", kind="tasks", now=self.now)

        self.assertEqual([row["id"] for row in first], [row["id"] for row in second])
        positions = {row["id"]: index for index, row in enumerate(first)}
        self.assertLess(positions[f"task:{overdue.id}"], positions[f"task:{due.id}"])
        self.assertLess(positions[f"task:{due.id}"], positions[f"task:{active.id}"])
        overdue.refresh_from_db()
        due.refresh_from_db()
        active.refresh_from_db()
        self.assertIsNone(overdue.completed_at)
        self.assertIsNone(due.completed_at)
        self.assertIsNone(active.completed_at)

    def test_family_timezone_controls_today_across_dst_boundary(self):
        # 2026-10-24 22:30 UTC is already 2026-10-25 locally in Berlin,
        # immediately before the autumn DST transition.
        locally_today = self.task("Local today", due_at=datetime(2026, 10, 24, 22, 30, tzinfo=UTC))
        locally_yesterday = self.task("Local yesterday", due_at=datetime(2026, 10, 24, 21, 30, tzinfo=UTC))

        rows = project_actions(user=self.alice, family=self.family, scope="today", kind="tasks", now=self.now)
        by_id = {row["id"]: row for row in rows}

        self.assertEqual(by_id[f"task:{locally_today.id}"]["state"], "due")
        self.assertEqual(by_id[f"task:{locally_yesterday.id}"]["state"], "overdue")

    def test_routine_projection_uses_bounded_history_without_n_plus_one(self):
        routine = Routine.objects.create(family=self.family, name="Viele Logs", target_count=1, target_period_days=7)
        for index in range(MAX_ROUTINE_LOGS + 8):
            RoutineLog.objects.create(
                routine=routine,
                done_at=self.now - timedelta(days=MAX_ROUTINE_LOGS + 8 - index),
                done_by=self.alice,
            )

        with CaptureQueriesContext(connection) as captured:
            rows = project_actions(user=self.alice, family=self.family, scope="routines", now=self.now)

        row = next(item for item in rows if item["id"] == f"routine:{routine.id}")
        self.assertLessEqual(row["repeat"]["prediction"]["sample_count"], MAX_ROUTINE_LOGS)
        self.assertLessEqual(len(captured), 5)

    def test_recent_scope_includes_recent_task_and_routine_activity_only(self):
        recent_task = self.task("Recently done", completed_at=self.now - timedelta(days=2))
        old_task = self.task("Old done", completed_at=self.now - timedelta(days=40))
        recent_routine = Routine.objects.create(family=self.family, name="Recent routine", target_count=1, target_period_days=7)
        old_routine = Routine.objects.create(family=self.family, name="Old routine", target_count=1, target_period_days=7)
        RoutineLog.objects.create(routine=recent_routine, done_at=self.now - timedelta(days=2), done_by=self.alice)
        RoutineLog.objects.create(routine=old_routine, done_at=self.now - timedelta(days=40), done_by=self.alice)

        rows = project_actions(user=self.alice, family=self.family, scope="recent", now=self.now)
        ids = {row["id"] for row in rows}

        self.assertIn(f"task:{recent_task.id}", ids)
        self.assertIn(f"routine:{recent_routine.id}", ids)
        self.assertNotIn(f"task:{old_task.id}", ids)
        self.assertNotIn(f"routine:{old_routine.id}", ids)

    def test_invalid_filters_return_400(self):
        response = self.client.get(f"/api/actions/?family={self.family.id}&scope=magic")
        self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/actions/?family=not-a-uuid")
        self.assertEqual(response.status_code, 400)
