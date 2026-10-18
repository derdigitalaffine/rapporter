from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .meal_models import (
    MealDish,
    MealIngredient,
    MealPlanDayTag,
    MealPlanEntry,
    MealPlanTemplate,
    MealTag,
)
from .meal_service import aggregate_meal_demand, build_transfer_diff, commit_transfer
from .models import Family, Membership, ShoppingItem, ShoppingList


class MealPlanningTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(username="meal-alice", password="pass-123")
        self.bob = User.objects.create_user(username="meal-bob", password="pass-123")
        self.family = Family.objects.create(name="Meal Family", slug="meal-family")
        self.other = Family.objects.create(name="Other Meal Family", slug="other-meal-family")
        Membership.objects.create(family=self.family, user=self.alice, role=Membership.Role.OWNER, display_name="Alice")
        Membership.objects.create(family=self.other, user=self.bob, role=Membership.Role.OWNER, display_name="Bob")
        self.shopping = ShoppingList.objects.create(family=self.family, name="Einkauf")
        self.other_shopping = ShoppingList.objects.create(family=self.other, name="Geheim")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def _dish(self):
        dish = MealDish.objects.create(
            family=self.family,
            name="Suppe",
            default_servings=2,
            favorite=True,
            created_by=self.alice,
        )
        MealIngredient.objects.create(dish=dish, name="Karotten", quantity=Decimal("4"), unit="Stück")
        MealIngredient.objects.create(dish=dish, name="Salz", quantity=Decimal("1"), unit="TL", normally_on_hand=True)
        return dish

    def _planned_dish(self, servings=4):
        dish = self._dish()
        return MealPlanEntry.objects.create(
            family=self.family,
            date=date(2026, 10, 19),
            slot="Abendessen",
            dish=dish,
            servings=servings,
            created_by=self.alice,
        )

    def _selection(self):
        demand = aggregate_meal_demand(self.family, date(2026, 10, 19), date(2026, 10, 19))
        return {
            row["key"]: {"missing": row["name"] == "Karotten"}
            for row in demand
        }

    def test_demand_scales_servings_and_marks_staples(self):
        self._planned_dish(servings=4)
        demand = aggregate_meal_demand(self.family, date(2026, 10, 19), date(2026, 10, 19))
        rows = {row["name"]: row for row in demand}
        self.assertEqual(rows["Karotten"]["quantity_value"], "8")
        self.assertEqual(rows["Karotten"]["quantity_text"], "8 Stück")
        self.assertFalse(rows["Karotten"]["normally_on_hand"])
        self.assertEqual(rows["Salz"]["quantity_text"], "2 TL")
        self.assertTrue(rows["Salz"]["normally_on_hand"])

    def test_free_leftovers_entry_does_not_create_demand(self):
        MealPlanEntry.objects.create(
            family=self.family,
            date=date(2026, 10, 19),
            slot="Mittagessen",
            title="Reste",
            created_by=self.alice,
        )
        self.assertEqual(aggregate_meal_demand(self.family, date(2026, 10, 19), date(2026, 10, 19)), [])

    def test_shopping_transfer_is_explicit_and_idempotent(self):
        self._planned_dish()
        selection = self._selection()
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.shopping).count(), 0)

        first = commit_transfer(
            user=self.alice,
            family=self.family,
            start_date=date(2026, 10, 19),
            end_date=date(2026, 10, 19),
            shopping_list=self.shopping,
            selection=selection,
        )
        self.assertIn("add", first["applied"])
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.shopping).count(), 1)
        item = ShoppingItem.objects.get(shopping_list=self.shopping)
        self.assertEqual(item.name, "Karotten")
        self.assertEqual(item.quantity, "8 Stück")

        second = commit_transfer(
            user=self.alice,
            family=self.family,
            start_date=date(2026, 10, 19),
            end_date=date(2026, 10, 19),
            shopping_list=self.shopping,
            selection=selection,
        )
        self.assertEqual(second["applied"], [])
        self.assertEqual(ShoppingItem.objects.filter(shopping_list=self.shopping).count(), 1)

    def test_checked_shopping_item_is_preserved_on_plan_update(self):
        entry = self._planned_dish()
        selection = self._selection()
        commit_transfer(
            user=self.alice,
            family=self.family,
            start_date=entry.date,
            end_date=entry.date,
            shopping_list=self.shopping,
            selection=selection,
        )
        item = ShoppingItem.objects.get(shopping_list=self.shopping)
        item.checked = True
        item.save(update_fields=["checked"])
        entry.servings = 6
        entry.save(update_fields=["servings"])
        new_selection = self._selection()

        diff = build_transfer_diff(
            user=self.alice,
            family=self.family,
            start_date=entry.date,
            end_date=entry.date,
            shopping_list=self.shopping,
            selection=new_selection,
        )
        self.assertIn("preserve_checked", {action["action"] for action in diff})
        commit_transfer(
            user=self.alice,
            family=self.family,
            start_date=entry.date,
            end_date=entry.date,
            shopping_list=self.shopping,
            selection=new_selection,
        )
        item.refresh_from_db()
        self.assertEqual(item.quantity, "8 Stück")

    def test_manually_changed_shopping_item_is_preserved(self):
        entry = self._planned_dish()
        selection = self._selection()
        commit_transfer(
            user=self.alice,
            family=self.family,
            start_date=entry.date,
            end_date=entry.date,
            shopping_list=self.shopping,
            selection=selection,
        )
        item = ShoppingItem.objects.get(shopping_list=self.shopping)
        item.quantity = "schon fast genug"
        item.save(update_fields=["quantity"])
        entry.servings = 6
        entry.save(update_fields=["servings"])
        diff = build_transfer_diff(
            user=self.alice,
            family=self.family,
            start_date=entry.date,
            end_date=entry.date,
            shopping_list=self.shopping,
            selection=self._selection(),
        )
        self.assertIn("preserve_modified", {action["action"] for action in diff})
        commit_transfer(
            user=self.alice,
            family=self.family,
            start_date=entry.date,
            end_date=entry.date,
            shopping_list=self.shopping,
            selection=self._selection(),
        )
        item.refresh_from_db()
        self.assertEqual(item.quantity, "schon fast genug")

    def test_api_rejects_cross_family_reads_and_relations(self):
        secret = MealDish.objects.create(family=self.other, name="Geheimrezept", created_by=self.bob)
        response = self.client.get(f"/api/meal-dishes/{secret.id}/")
        self.assertEqual(response.status_code, 404)

        foreign_tag = MealTag.objects.create(family=self.other, name="Geheim")
        response = self.client.post(
            "/api/meal-dishes/",
            {
                "family": str(self.family.id),
                "name": "Eigenes Gericht",
                "default_servings": 2,
                "tags": [str(foreign_tag.id)],
                "ingredients": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.get(f"/api/meal-plan/shopping-preview/?family={self.other.id}&start=2026-10-19&end=2026-10-19")
        self.assertEqual(response.status_code, 403)

    def test_api_rejects_foreign_shopping_list_transfer(self):
        self._planned_dish()
        response = self.client.post(
            "/api/meal-plan/shopping-commit/",
            {
                "family": str(self.family.id),
                "start": "2026-10-19",
                "end": "2026-10-19",
                "shopping_list": str(self.other_shopping.id),
                "selection": self._selection(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ShoppingItem.objects.filter(shopping_list=self.other_shopping).exists())

    def test_template_snapshot_and_apply_preserves_motto_tags(self):
        dish = self._dish()
        soup_day = MealTag.objects.create(family=self.family, name="Suppentag")
        entry = MealPlanEntry.objects.create(
            family=self.family,
            date=date(2026, 10, 19),
            slot="Abendessen",
            dish=dish,
            created_by=self.alice,
        )
        entry.tags.add(soup_day)
        MealPlanDayTag.objects.create(family=self.family, date=entry.date, tag=soup_day)

        response = self.client.post(
            "/api/meal-plan/templates/from-week/",
            {"family": str(self.family.id), "week_start": "2026-10-19", "name": "Motto-Woche"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        template = MealPlanTemplate.objects.get(pk=response.data["id"])
        self.assertEqual(template.entries.count(), 1)
        self.assertEqual(template.day_tags.count(), 1)

        response = self.client.post(
            f"/api/meal-plan/templates/{template.id}/apply/",
            {"week_start": "2026-10-26"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        applied = MealPlanEntry.objects.get(family=self.family, date=date(2026, 10, 26), slot="Abendessen")
        self.assertEqual(applied.dish_id, dish.id)
        self.assertTrue(applied.tags.filter(pk=soup_day.pk).exists())
        self.assertTrue(MealPlanDayTag.objects.filter(family=self.family, date=date(2026, 10, 26), tag=soup_day).exists())
