from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .memory import normalize_name
from .models import (
    Family,
    Membership,
    Routine,
    RoutineLog,
    ShoppingItem,
    ShoppingList,
    ShoppingPredictionFeedback,
    ShoppingPurchaseEvent,
)
from .predictions import routine_prediction, shopping_predictions


class PredictionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="prediction-owner", password="test-pass-123")
        self.other = User.objects.create_user(username="other-owner", password="test-pass-123")
        self.family = Family.objects.create(name="Prediction Family", slug="prediction-family", timezone="Europe/Berlin")
        self.other_family = Family.objects.create(name="Other Family", slug="other-prediction-family", timezone="Europe/Berlin")
        Membership.objects.create(family=self.family, user=self.user, role=Membership.Role.OWNER)
        Membership.objects.create(family=self.other_family, user=self.other, role=Membership.Role.OWNER)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.shopping = ShoppingList.objects.create(family=self.family, name="Supermarkt", store="Markt")

    def test_routine_serializer_hides_manual_interval_and_returns_prediction(self):
        routine = Routine.objects.create(family=self.family, name="Bad putzen", suggested_interval_days=3)
        RoutineLog.objects.create(routine=routine, done_at=timezone.now() - timedelta(days=7), done_by=self.user)

        response = self.client.get("/api/routines/")

        self.assertEqual(response.status_code, 200)
        rows = response.data.get("results", response.data)
        row = next(item for item in rows if str(item["id"]) == str(routine.id))
        self.assertNotIn("suggested_interval_days", row)
        self.assertEqual(row["prediction"]["status"], "not_enough_data")
        self.assertEqual(row["prediction"]["sample_count"], 1)

    def test_regular_routine_logs_learn_seven_day_cycle(self):
        now = timezone.now().replace(microsecond=0)
        routine = Routine.objects.create(family=self.family, name="Bettwäsche")
        for days in (35, 28, 21, 14, 7):
            RoutineLog.objects.create(routine=routine, done_at=now - timedelta(days=days), done_by=self.user)

        prediction = routine_prediction(routine, now=now)

        self.assertEqual(prediction["expected_interval_days"], 7.0)
        self.assertGreaterEqual(prediction["confidence"], 0.7)
        self.assertEqual(prediction["status"], "due")
        self.assertEqual(prediction["days_until_expected"], 0)

    def test_irregular_routine_stays_in_learning_state(self):
        now = timezone.now().replace(microsecond=0)
        routine = Routine.objects.create(family=self.family, name="Keller")
        offsets = [31, 29, 15, 11, 0]
        for days in offsets:
            RoutineLog.objects.create(routine=routine, done_at=now - timedelta(days=days), done_by=self.user)

        prediction = routine_prediction(routine, now=now)

        self.assertEqual(prediction["status"], "learning")
        self.assertLess(prediction["confidence"], 0.55)
        self.assertEqual(prediction["interval_count"], 4)

    def test_checking_item_via_patch_creates_exactly_one_purchase_event(self):
        item = ShoppingItem.objects.create(
            shopping_list=self.shopping,
            name="Milch",
            quantity="2",
            category="Molkerei",
            aisle="Kühlung",
            added_by=self.user,
        )

        checked = self.client.patch(f"/api/shopping-items/{item.id}/", {"checked": True}, format="json")
        changed = self.client.patch(f"/api/shopping-items/{item.id}/", {"note": "Bio"}, format="json")

        self.assertEqual(checked.status_code, 200)
        self.assertEqual(changed.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.checked)
        self.assertIsNotNone(item.checked_at)
        events = ShoppingPurchaseEvent.objects.filter(source_item_id=item.id)
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.normalized_name, normalize_name("Milch"))
        self.assertEqual(event.quantity, "2")
        self.assertEqual(event.store, "Markt")

    def test_clearing_checked_items_keeps_purchase_history(self):
        item = ShoppingItem.objects.create(shopping_list=self.shopping, name="Brot", added_by=self.user)
        self.client.patch(f"/api/shopping-items/{item.id}/", {"checked": True}, format="json")
        self.assertEqual(ShoppingPurchaseEvent.objects.filter(source_item_id=item.id).count(), 1)

        response = self.client.post(f"/api/smart/shopping-lists/{self.shopping.id}/clear-checked/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ShoppingItem.objects.filter(id=item.id).exists())
        self.assertEqual(ShoppingPurchaseEvent.objects.filter(source_item_id=item.id).count(), 1)

    def _purchase_history(self, name="Milch"):
        now = timezone.now().replace(microsecond=0)
        for days in (21, 16, 11, 6):
            ShoppingPurchaseEvent.objects.create(
                family=self.family,
                shopping_list=self.shopping,
                normalized_name=normalize_name(name),
                display_name=name,
                quantity="2",
                category="Molkerei",
                aisle="Kühlung",
                store="Markt",
                purchased_at=now - timedelta(days=days),
                purchased_by=self.user,
            )
        return now

    def test_recurring_purchase_is_predicted_and_open_item_suppresses_it(self):
        now = self._purchase_history()

        result = shopping_predictions(self.family, now=now)

        suggestion = next(item for item in result["suggestions"] if item["key"] == normalize_name("Milch"))
        self.assertEqual(suggestion["prediction"]["expected_interval_days"], 5.0)
        self.assertIn(suggestion["prediction"]["status"], {"due", "overdue"})
        self.assertEqual(suggestion["defaults"]["quantity"], "2")

        ShoppingItem.objects.create(shopping_list=self.shopping, name="milch", added_by=self.user)
        suppressed = shopping_predictions(self.family, now=now)
        self.assertNotIn(normalize_name("Milch"), {item["key"] for item in suppressed["suggestions"]})

    def test_prediction_api_accepts_and_dismisses_without_cross_family_access(self):
        self._purchase_history()

        response = self.client.get(f"/api/shopping-predictions/?family={self.family.id}")
        self.assertEqual(response.status_code, 200)
        suggestion = next(item for item in response.data["suggestions"] if item["key"] == normalize_name("Milch"))

        accepted = self.client.post(
            "/api/shopping-predictions/accept/",
            {"family": str(self.family.id), "key": suggestion["key"], "list": str(self.shopping.id)},
            format="json",
        )
        self.assertEqual(accepted.status_code, 201)
        self.assertTrue(ShoppingItem.objects.filter(shopping_list=self.shopping, name="Milch", checked=False).exists())

        ShoppingItem.objects.filter(shopping_list=self.shopping, name__iexact="Milch").delete()
        dismissed = self.client.post(
            "/api/shopping-predictions/feedback/",
            {"family": str(self.family.id), "key": suggestion["key"], "action": "dismissed"},
            format="json",
        )
        self.assertEqual(dismissed.status_code, 200)
        feedback = ShoppingPredictionFeedback.objects.get(family=self.family, normalized_name=normalize_name("Milch"))
        self.assertGreater(feedback.suppress_until, timezone.now())
        hidden = self.client.get(f"/api/shopping-predictions/?family={self.family.id}")
        self.assertNotIn(normalize_name("Milch"), {item["key"] for item in hidden.data["suggestions"]})

        forbidden = self.client.get(f"/api/shopping-predictions/?family={self.other_family.id}")
        self.assertEqual(forbidden.status_code, 403)
