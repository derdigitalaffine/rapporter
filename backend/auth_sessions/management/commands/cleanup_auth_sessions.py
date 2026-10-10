from django.core.management.base import BaseCommand

from auth_sessions.service import prune_old_sessions


class Command(BaseCommand):
    help = "Delete revoked or long-expired auth sessions after the configured retention period."

    def handle(self, *args, **options):
        deleted = prune_old_sessions()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} old auth session(s)."))
