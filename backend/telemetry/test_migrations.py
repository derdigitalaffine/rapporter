from django.core.management import call_command
from django.test import TestCase


class TelemetryMigrationDriftTests(TestCase):
    def test_telemetry_models_have_no_uncommitted_migration_changes(self):
        call_command("makemigrations", "telemetry", check=True, dry_run=True, verbosity=0)
