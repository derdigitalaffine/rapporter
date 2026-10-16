from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .action_capture_ranking import rank_capture_suggestions
from .models import Family, Membership, Task
from .unified_action_models import ActionCompletion


UTC = dt_timezone.utc


class ActionCaptureRankingTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)

    def test_context_reorders_only_near_text_matches(self):
        rows = [
            {"id": "task:strong", "title": "Betten machen", "state": "active", "capture_match": 0.63, "capture_reason": "available"},
            {"id": "task:habit", "title": "Betten richten", "state": "active", "capture_match": 0.60, "capture_reason": "available"},
        ]
        history = {"task:habit": [self.now - timedelta(weeks=value) for value in range(4)]}
        ranked = rank_capture_suggestions(rows, history, self.now)
        self.assertEqual(ranked[0]["id"], "task:habit")
        self.assertEqual(ranked[0]["capture_reason"], "history_weekday")
        self.assertIn("Wochentag", ranked[0]["capture_explanation"])

    def test_strong_text_match_stays_ahead_of_context_only_candidate(self):
        rows = [
            {"id": "task:strong", "title": "Hund füttern", "state": "active", "capture_match": 0.92, "capture_reason": "title_match"},
            {"id": "task:weak", "title": "Hund rausbringen", "state": "due", "capture_match": 0.40, "capture_reason": "available"},
        ]
        history = {"task:weak": [self.now - timedelta(weeks=value) for value in range(10)]}
        ranked = rank_capture_suggestions(rows, history, self.now)
        self.assertEqual(ranked[0]["id"], "task:strong")
        self.assertEqual(ranked[0]["capture_reason"], "title_match")

    def test_strongest_reason_and_tie_break_are_deterministic(self):
        observations = [self.now - timedelta(weeks=value) for value in range(3)]
        rows = [
            {"id": "task:b", "title": "Beta", "state": "due", "capture_match": 0.5, "capture_reason": "available"},
            {"id": "task:a", "title": "Alpha", "state": "due", "capture_match": 0.5, "capture_reason": "available"},
        ]
        histories = {"task:a": observations, "task:b": observations}
        first = rank_capture_suggestions(rows, histories, self.now)
        second = rank_capture_suggestions(list(reversed(rows)), histories, self.now)
        self.assertEqual([row["id"] for row in first], ["task:a", "task:b"])
        self.assertEqual([row["id"] for row in first], [row["id"] for row in second])
        self.assertEqual(first[0]["capture_reason"], "due_now")

    def test_source_rows_are_not_mutated(self):
        row = {"id": "task:a", "title": "Alpha", "state": "active", "capture_match": 0.5, "capture_reason": "available"}
        original = dict(row)
        rank_capture_suggestions([row], {}, self.now)
        self.assertEqual(row, original)


class ActionCaptureRankingIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="capture-ranker")
        self.family = Family.objects.create(name="Capture", slug="capture")
        Membership.objects.create(user=self.user, family=self.family, role="owner")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.strong = Task.objects.create(family=self.family, title="Betten machen", created_by=self.user)
        self.habit = Task.objects.create(family=self.family, title="Betten richten", created_by=self.user)

    def test_get_uses_history_without_mutating_and_stays_family_scoped(self):
        now = timezone.now()
        for weeks in range(4):
            ActionCompletion.objects.create(
                action=self.habit.unified_action,
                actor=self.user,
                request_id=uuid4(),
                occurred_at=now - timedelta(weeks=weeks),
            )
        foreign = Family.objects.create(name="Foreign", slug="foreign-capture")
        foreign_task = Task.objects.create(family=foreign, title="Betten richten", created_by=self.user)
        before = ActionCompletion.objects.count()

        response = self.client.get(f"/api/actions/capture/?family={self.family.id}&q=betten")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ActionCompletion.objects.count(), before)
        ids = [row["id"] for row in response.data["suggestions"]]
        self.assertEqual(ids[0], f"task:{self.habit.id}")
        self.assertNotIn(f"task:{foreign_task.id}", ids)
        self.assertEqual(response.data["suggestions"][0]["capture_reason"], "history_weekday")
        self.assertTrue(response.data["suggestions"][0]["capture_explanation"])

    def test_get_falls_back_for_invalid_family_timezone(self):
        self.family.timezone = "Invalid/Legacy-Timezone"
        self.family.save(update_fields=["timezone"])

        response = self.client.get(f"/api/actions/capture/?family={self.family.id}&q=betten")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["suggestions"])
