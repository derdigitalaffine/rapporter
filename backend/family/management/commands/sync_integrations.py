from django.core.management.base import BaseCommand
from family.automation import run_all_rules
from family.extended_integrations import sync_source
from family.models import IntegrationSource


class Command(BaseCommand):
    help = "Synchronize enabled integrations and execute fam-uh-le automation rules"

    def handle(self, *args, **options):
        total = 0
        for source in IntegrationSource.objects.filter(enabled=True):
            try:
                count = sync_source(source)
                total += count
                self.stdout.write(f"{source.name}: {count}")
            except Exception as exc:
                self.stderr.write(f"{source.name}: {exc}")
        executed = run_all_rules()
        self.stdout.write(self.style.SUCCESS(f"Synchronized {total} events; executed {executed} automation actions"))
