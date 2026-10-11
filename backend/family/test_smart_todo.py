from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Family, Membership, Routine, RoutineLog, RoutineReminderState, Task, TaskList
from .todo_models import TodoActionPreference, TodoPreference


UTC = dt_timezone.utc


class SmartTodoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="alice-smart-todo", password="test-pass-123")
        self.bob = User.objects.create_user(username="bob-smart-todo", password="test-pass-123")
        self.family = Family.objects.create(name="Smart Todo", slug="smart-todo", timezone="Europe/Berlin")
        self.other = Family.objects.create(name="Other Smart Todo", slug="other-smart-todo", timezone="Europe/Berlin")
        self.membership = Membership.objects.create(family=self.family, user=self.alice, role=Membership.Role.OWNER)
        self.other_membership = Membership.objects.create(family=self.other, user=self.bob, role=Membership.Role.OWNER)
        self.task_list = TaskList.objects.create(family=self.family, name="Alltag")
        self.other_list = TaskList.objects.create(family=self.other, name="Privat")
        self.now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def task(self, title, **kwargs):
        defaults = {
            "family": self.family,
            "task_list": self.task_list,
            "created_by": self.alice,
            "title": title,
        }
        defaults.update(kwargs)
        return Task.objects.create(**defaults)

    def get_actions(self, scope="today"):
        with patch("family.action_projection.timezone.now", return_value=self.now), patch(
            "family.todo_ranking.timezone.now", return_value=self.now
        ):
            return self.client.get(f"/api/actions/?family={self.family.id}&scope={scope}")

    def patch_preferences(self, payload):
        with patch("family.action_projection.timezone.now", return_value=self.now):
            return self.client.patch(
                f"/api/actions/?family={self.family.id}",
                payload,
                format="json",
            )

    def test_real_actions_response_exposes_results_alias_focus_and_versions(self):
        task = self.task("Heute", due_at=self.now)
        response = self.get_actions()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["actions"], response.data["results"])
        self.assertEqual(response.data["ranking_version"], "actions-v1")
        self.assertEqual(response.data["focus_ranking_version"], "todo-focus-v1")
        self.assertEqual(response.data["focus"][0]["id"], f"task:{task.id}")
        self.assertIn("due_today", response.data["focus"][0]["smart"]["reasons"])

    def test_manual_pin_beats_canonical_ranking_and_is_explainable(self):
        overdue = self.task("Überfällig", due_at=self.now - timedelta(days=1))
        due = self.task("Angepinnt", due_at=self.now)
        action_id = f"task:{due.id}"
        response = self.patch_preferences({"action_id": action_id, "pinned": True})
        self.assertEqual(response.status_code, 200)

        response = self.get_actions()
        self.assertEqual(response.data["focus"][0]["id"], action_id)
        self.assertIn("pinned", response.data["focus"][0]["smart"]["reasons"])
        self.assertIn(f"task:{overdue.id}", [row["id"] for row in response.data["focus"]])

    def test_hide_removes_only_focus_not_canonical_action(self):
        task = self.task("Nicht im Fokus", due_at=self.now)
        action_id = f"task:{task.id}"
        response = self.patch_preferences({"action_id": action_id, "hidden_from_focus": True})
        self.assertEqual(response.status_code, 200)

        response = self.get_actions()
        self.assertIn(action_id, [row["id"] for row in response.data["actions"]])
        self.assertNotIn(action_id, [row["id"] for row in response.data["focus"]])

    def test_smart_ranking_can_be_disabled_without_mutating_domain_rows(self):
        task = self.task("Unverändert", due_at=self.now)
        before = (task.completed_at, RoutineLog.objects.count())
        response = self.patch_preferences({"smart_ranking_enabled": False})
        self.assertEqual(response.status_code, 200)
        response = self.get_actions()
        self.assertEqual(response.data["focus"], [])
        self.assertFalse(response.data["preferences"]["smart_ranking_enabled"])
        task.refresh_from_db()
        self.assertEqual((task.completed_at, RoutineLog.objects.count()), before)

    def test_chronological_sort_is_stable_and_explicit(self):
        later = self.task("Später", due_at=self.now + timedelta(hours=3), priority=Task.Priority.HIGH)
        earlier = self.task("Früher", due_at=self.now + timedelta(hours=1))
        response = self.patch_preferences({"today_sort": "chronological"})
        self.assertEqual(response.status_code, 200)
        first = self.get_actions()
        second = self.get_actions()
        first_ids = [row["id"] for row in first.data["actions"]]
        self.assertEqual(first_ids, [row["id"] for row in second.data["actions"]])
        self.assertLess(first_ids.index(f"task:{earlier.id}"), first_ids.index(f"task:{later.id}"))

    def test_snoozed_routine_and_done_today_are_not_suggested(self):
        routine = Routine.objects.create(family=self.family, name="Später erinnern", target_count=1, target_period_days=1)
        Routine.objects.filter(pk=routine.pk).update(created_at=self.now - timedelta(days=3))
        RoutineReminderState.objects.create(
            routine=routine,
            membership=self.membership,
            snoozed_until=self.now + timedelta(hours=4),
        )
        done = self.task("Schon fertig", completed_at=self.now - timedelta(minutes=5))
        response = self.get_actions()
        action_ids = [row["id"] for row in response.data["actions"]]
        focus_ids = [row["id"] for row in response.data["focus"]]
        self.assertIn(f"routine:{routine.id}", action_ids)
        self.assertIn(f"task:{done.id}", action_ids)
        self.assertNotIn(f"routine:{routine.id}", focus_ids)
        self.assertNotIn(f"task:{done.id}", focus_ids)

    def test_foreign_or_invisible_action_cannot_create_preference(self):
        foreign = Task.objects.create(
            family=self.other,
            task_list=self.other_list,
            created_by=self.bob,
            title="Fremd",
            due_at=self.now,
        )
        response = self.patch_preferences({"action_id": f"task:{foreign.id}", "pinned": True})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(TodoActionPreference.objects.count(), 0)

        response = self.client.patch(
            f"/api/actions/?family={self.other.id}",
            {"smart_ranking_enabled": False},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TodoPreference.objects.filter(membership=self.other_membership).exists())

    def test_reset_clears_explicit_overrides_only(self):
        task = self.task("Reset", due_at=self.now)
        action_id = f"task:{task.id}"
        self.patch_preferences({"smart_ranking_enabled": False, "today_sort": "chronological"})
        self.patch_preferences({"action_id": action_id, "pinned": True, "hidden_from_focus": True})
        response = self.patch_preferences({"reset": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {
                "smart_ranking_enabled": True,
                "today_sort": "smart",
                "pinned_action_ids": [],
                "hidden_focus_action_ids": [],
            },
        )
        self.assertFalse(TodoActionPreference.objects.filter(membership=self.membership).exists())
