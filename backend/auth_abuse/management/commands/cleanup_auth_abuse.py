from django.core.management.base import BaseCommand

from auth_abuse.service import prune_expired


class Command(BaseCommand):
    help = "Delete expired auth-abuse buckets after the configured retention period."

    def handle(self, *args, **options):
        deleted = prune_expired()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired auth-abuse bucket(s)."))
