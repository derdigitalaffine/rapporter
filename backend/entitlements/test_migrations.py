from django.core.management import call_command
from django.test import TestCase


class EntitlementMigrationDriftTests(TestCase):
    def test_entitlement_models_have_no_uncommitted_migration_changes(self):
        call_command("makemigrations", "entitlements", check=True, dry_run=True, verbosity=0)
