from django.core.management.base import BaseCommand

from pets.reminders import process_pet_reminders


class Command(BaseCommand):
    help = "Send idempotent pet medication and prevention reminders that are due now."

    def handle(self, *args, **options):
        count = process_pet_reminders()
        self.stdout.write(f"pet reminders sent: {count}")
