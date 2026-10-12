from datetime import datetime, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from .action_projection import project_actions
from .models import Family, Membership, Task, TaskList


UTC = dt_timezone.utc


class TaskDuelActionProjectionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="duel-action-user", password="test-pass-123")
        self.family = Family.objects.create(
            name="Duel Action Family",
            slug="duel-action-family",
            timezone="Europe/Berlin",
        )
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        self.task_list = TaskList.objects.create(family=self.family, name="Allgemein")
        self.now = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)

    def task(self, title, **kwargs):
        return Task.objects.create(
            family=self.family,
            task_list=self.task_list,
            created_by=self.user,
            title=title,
            **kwargs,
        )

    def test_open_task_exposes_games_deep_link_and_completed_task_does_not(self):
        open_task = self.task("Ausspielen")
        completed_task = self.task("Erledigt", completed_at=self.now - timedelta(hours=1))

        rows = project_actions(
            user=self.user,
            family=self.family,
            scope="all",
            kind="tasks",
            now=self.now,
        )
        by_id = {row["id"]: row for row in rows}
        duel = next(
            action
            for action in by_id[f"task:{open_task.id}"]["allowed_actions"]
            if action["id"] == "duel"
        )

        self.assertEqual(duel["method"], "GET")
        self.assertEqual(
            duel["href"],
            f"/?page=games&family={self.family.id}&task={open_task.id}",
        )
        self.assertNotIn(
            "duel",
            {action["id"] for action in by_id[f"task:{completed_task.id}"]["allowed_actions"]},
        )
