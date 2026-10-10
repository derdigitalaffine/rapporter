from io import StringIO

from django.core.management import call_command
from django.test import TransactionTestCase


class BabyMigrationPreview(TransactionTestCase):
    reset_sequences = True

    def test_print_generated_migration(self):
        output = StringIO()
        call_command("makemigrations", "baby", dry_run=True, verbosity=3, stdout=output)
        print("\n=== BABY MIGRATION PREVIEW ===\n" + output.getvalue() + "\n=== END BABY MIGRATION PREVIEW ===")
