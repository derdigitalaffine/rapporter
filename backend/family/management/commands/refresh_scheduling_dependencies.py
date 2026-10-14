from django.core.management.base import BaseCommand

from family.scheduling_dependencies import refresh_dependency
from family.scheduling_models import SchedulingDependency


class Command(BaseCommand):
    help = "Refresh enabled relative scheduling dependencies inside the rolling materialization horizon."

    def add_arguments(self, parser):
        parser.add_argument("--family", dest="family_id", default=None)
        parser.add_argument("--horizon-days", type=int, default=120)

    def handle(self, *args, **options):
        horizon = options["horizon_days"]
        if not 1 <= horizon <= 730:
            raise ValueError("--horizon-days must be between 1 and 730")
        rows = SchedulingDependency.objects.filter(enabled=True).select_related("family")
        if options.get("family_id"):
            rows = rows.filter(family_id=options["family_id"])
        dependencies = 0
        outputs = 0
        for dependency in rows.iterator():
            dependencies += 1
            outputs += len(refresh_dependency(dependency, horizon_days=horizon))
        self.stdout.write(self.style.SUCCESS(f"Refreshed {dependencies} dependencies; {outputs} projected/materialized outputs."))
