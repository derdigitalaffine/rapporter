from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from .action_projection import project_actions
from .models import Family, Membership, Routine, Task, TaskList


class ActionDeleteProjectionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="todo-delete", password="test-pass-123")
        self.family = Family.objects.create(name="Todo Delete Family", slug="todo-delete-family", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.task_list = TaskList.objects.create(family=self.family, name="Allgemein")
        self.now = datetime(2026, 10, 11, 12, 0, tzinfo=dt_timezone.utc)

    def test_tasks_expose_canonical_delete_while_routines_do_not(self):
        task = Task.objects.create(
            family=self.family,
            task_list=self.task_list,
            created_by=self.user,
            title="Aufräumen",
            due_at=self.now,
        )
        routine = Routine.objects.create(
            family=self.family,
            name="Lüften",
            target_count=1,
            target_period_days=1,
        )

        rows = project_actions(user=self.user, family=self.family, scope="all", now=self.now)
        task_row = next(row for row in rows if row["id"] == f"task:{task.id}")
        routine_row = next(row for row in rows if row["id"] == f"routine:{routine.id}")

        self.assertIn(
            {"id": "delete", "method": "DELETE", "href": f"/api/tasks/{task.id}/"},
            task_row["allowed_actions"],
        )
        self.assertFalse(any(action["id"] == "delete" for action in routine_row["allowed_actions"]))
