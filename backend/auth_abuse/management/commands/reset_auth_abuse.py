from django.core.management.base import BaseCommand, CommandError

from auth_abuse.models import AuthAbuseBucket
from auth_abuse.service import POLICIES


class Command(BaseCommand):
    help = "Ops-only break-glass reset for auth-abuse counters; no HTTP endpoint is exposed."

    def add_arguments(self, parser):
        parser.add_argument("--scope", choices=sorted(POLICIES))
        parser.add_argument("--all", action="store_true", dest="reset_all")

    def handle(self, *args, **options):
        scope = options.get("scope")
        reset_all = options.get("reset_all")
        if bool(scope) == bool(reset_all):
            raise CommandError("Specify exactly one of --scope or --all.")
        queryset = AuthAbuseBucket.objects.all()
        if scope:
            queryset = queryset.filter(scope=scope)
        deleted, _ = queryset.delete()
        target = scope or "all scopes"
        self.stdout.write(self.style.WARNING(f"Reset {deleted} auth-abuse bucket(s) for {target}."))
