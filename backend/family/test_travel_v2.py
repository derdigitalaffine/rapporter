from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .context_links import ContextRef, default_context_registry
from .models import Family, FamilyEvent, Membership
from .travel_models import Trip


class TravelV2LifecycleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("travel-v2-owner")
        self.family = Family.objects.create(name="Travel V2", slug="travel-v2")
        Membership.objects.create(
            family=self.family,
            user=self.owner,
            role=Membership.Role.OWNER,
            display_name="Owner",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def post_trip(self, **extra):
        payload = {
            "family": str(self.family.id),
            "title": "Japan",
            "destination": "Tokyo",
        }
        payload.update(extra)
        return self.client.post("/api/trips/", payload, format="json")

    def test_legacy_exact_dates_remain_compatible(self):
        response = self.post_trip(
            starts_on="2099-04-10",
            ends_on="2099-04-20",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["date_precision"], "exact")
        self.assertEqual(response.data["stage"], "scheduled")
        self.assertEqual(response.data["starts_on"], "2099-04-10")
        self.assertEqual(response.data["ends_on"], "2099-04-20")
        self.assertIsNotNone(response.data["calendar_event_id"])

    def test_unknown_year_season_and_month_trips_do_not_create_calendar_events(self):
        cases = [
            ({"stage": "idea", "date_precision": "unknown"}, "unknown"),
            ({"stage": "planning", "date_precision": "year", "date_year": 2099}, "year"),
            (
                {
                    "stage": "planning",
                    "date_precision": "season",
                    "date_year": 2099,
                    "date_season": "summer",
                },
                "season",
            ),
            (
                {
                    "stage": "planning",
                    "date_precision": "month",
                    "date_year": 2099,
                    "date_month": 7,
                },
                "month",
            ),
        ]
        for index, (payload, precision) in enumerate(cases):
            with self.subTest(precision=precision):
                response = self.post_trip(title=f"Trip {index}", **payload)
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["date_precision"], precision)
                self.assertIsNone(response.data["starts_on"])
                self.assertIsNone(response.data["ends_on"])
                self.assertIsNone(response.data.get("calendar_event_id"))
        self.assertEqual(FamilyEvent.objects.filter(type="travel.trip").count(), 0)

    def test_precision_transition_creates_and_removes_calendar_projection(self):
        created = self.post_trip(stage="idea", date_precision="unknown")
        self.assertEqual(created.status_code, 201, created.data)
        trip_id = created.data["id"]

        concrete = self.client.patch(
            f"/api/trips/{trip_id}/",
            {
                "stage": "scheduled",
                "date_precision": "range",
                "starts_on": "2099-06-01",
                "ends_on": "2099-06-14",
            },
            format="json",
        )
        self.assertEqual(concrete.status_code, 200, concrete.data)
        event_id = concrete.data["calendar_event_id"]
        self.assertIsNotNone(event_id)
        self.assertTrue(FamilyEvent.objects.filter(id=event_id, type="travel.trip").exists())

        approximate = self.client.patch(
            f"/api/trips/{trip_id}/",
            {
                "stage": "planning",
                "date_precision": "year",
                "date_year": 2100,
            },
            format="json",
        )
        self.assertEqual(approximate.status_code, 200, approximate.data)
        self.assertIsNone(approximate.data["starts_on"])
        self.assertIsNone(approximate.data["ends_on"])
        self.assertIsNone(approximate.data.get("calendar_event_id"))
        self.assertFalse(FamilyEvent.objects.filter(id=event_id).exists())

    def test_precision_and_stage_combinations_are_validated(self):
        missing_end = self.post_trip(
            stage="scheduled",
            date_precision="exact",
            starts_on="2099-01-01",
        )
        self.assertEqual(missing_end.status_code, 400)
        self.assertIn("ends_on", missing_end.data)

        invalid_month = self.post_trip(
            stage="planning",
            date_precision="month",
            date_year=2099,
            date_month=13,
        )
        self.assertEqual(invalid_month.status_code, 400)
        self.assertIn("date_month", invalid_month.data)

        impossible_stage = self.post_trip(stage="active", date_precision="unknown")
        self.assertEqual(impossible_stage.status_code, 400)
        self.assertIn("stage", impossible_stage.data)

        contradictory_archive = self.post_trip(
            stage="planning",
            archived=True,
            date_precision="unknown",
        )
        self.assertEqual(contradictory_archive.status_code, 400)
        self.assertIn("archived", contradictory_archive.data)

        reversed_dates = self.post_trip(
            stage="scheduled",
            date_precision="range",
            starts_on="2099-02-10",
            ends_on="2099-02-01",
        )
        self.assertEqual(reversed_dates.status_code, 400)
        self.assertIn("ends_on", reversed_dates.data)

    def test_legacy_archived_flag_and_stage_keep_context_lifecycle_in_sync(self):
        created = self.post_trip(stage="planning", date_precision="unknown")
        self.assertEqual(created.status_code, 201, created.data)
        trip_id = created.data["id"]

        archived = self.client.patch(
            f"/api/trips/{trip_id}/",
            {"archived": True},
            format="json",
        )
        self.assertEqual(archived.status_code, 200, archived.data)
        self.assertTrue(archived.data["archived"])
        self.assertEqual(archived.data["stage"], "archived")

        trip = Trip.objects.get(id=trip_id)
        registry = default_context_registry()
        ref = ContextRef("trip", trip.id)
        resolved = registry.resolve_many(self.owner, self.family, [ref])
        self.assertEqual(resolved[ref].lifecycle, "archived")

        restored = self.client.patch(
            f"/api/trips/{trip_id}/",
            {"archived": False},
            format="json",
        )
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertFalse(restored.data["archived"])
        self.assertEqual(restored.data["stage"], "planning")
        trip.refresh_from_db()
        resolved = registry.resolve_many(self.owner, self.family, [ref])
        self.assertEqual(resolved[ref].lifecycle, "available")
