from django.core.management.base import BaseCommand
from family.birthdays import run_birthday_reminders
from family.routine_reminders import run_routine_reminders
from family.notification_digests import flush_notification_batches
from family.automation import run_all_rules
from family.integration_health import sync_with_health
from family.models import Family, IntegrationSource


class Command(BaseCommand):
    help = "Synchronize enabled integrations and execute FamilyOS automation rules"

    def handle(self, *args, **options):
        total = 0
        for source in IntegrationSource.objects.filter(enabled=True, family__status=Family.Status.ACTIVE):
            try:
                count = sync_with_health(source)
                total += count
                self.stdout.write(f"{source.name}: {count}")
            except Exception as exc:
                self.stderr.write(f"{source.name}: {exc}")
        notifications = flush_notification_batches()
        self.stdout.write(f"Notification summaries: {notifications}")
        executed = run_all_rules()
        birthdays = run_birthday_reminders()
        self.stdout.write(f"Birthday reminders: {birthdays}")
        self.stdout.write(f"Routine reminders: {run_routine_reminders()}")
        self.stdout.write(self.style.SUCCESS(f"Synchronized {total} events; executed {executed} automation actions"))
