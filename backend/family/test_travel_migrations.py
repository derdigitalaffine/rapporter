from datetime import date
from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class TravelLifecycleMigrationTests(TransactionTestCase):
    migrate_from = [("family", "0212_boardpost_trip_kind")]
    migrate_to = [("family", "0213_trip_lifecycle_date_precision")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Family = old_apps.get_model("family", "Family")
        Trip = old_apps.get_model("family", "Trip")
        family = Family.objects.create(name="Migration Travel", slug="migration-travel")
        self.ids = {}
        rows = {
            "scheduled": dict(starts_on=date(2026, 10, 11), ends_on=date(2026, 10, 12), archived=False),
            "active": dict(starts_on=date(2026, 10, 1), ends_on=date(2026, 10, 20), archived=False),
            "completed": dict(starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 2), archived=False),
            "archived": dict(starts_on=date(2027, 1, 1), ends_on=date(2027, 1, 2), archived=True),
        }
        for expected_stage, values in rows.items():
            trip = Trip.objects.create(
                family=family,
                title=f"{expected_stage} trip",
                destination="",
                notes="",
                **values,
            )
            self.ids[expected_stage] = trip.id

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def assert_backfill(self):
        Trip = self.apps.get_model("family", "Trip")
        for expected_stage, trip_id in self.ids.items():
            trip = Trip.objects.get(id=trip_id)
            self.assertEqual(trip.date_precision, "exact")
            self.assertEqual(trip.stage, expected_stage)
            self.assertIsNotNone(trip.starts_on)
            self.assertIsNotNone(trip.ends_on)

    def test_exact_trip_backfill_is_deterministic_and_repeatable(self):
        self.assert_backfill()
        migration = import_module("family.migrations.0213_trip_lifecycle_date_precision")
        with connection.schema_editor() as schema_editor:
            migration.backfill_trip_lifecycle(self.apps, schema_editor)
            migration.backfill_trip_lifecycle(self.apps, schema_editor)
        self.assert_backfill()
