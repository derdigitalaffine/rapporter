from django.core.management.base import BaseCommand
from family.models import Family, RoutineLog, ShoppingPurchaseEvent, Task
from family.unified_action_models import ActionDomainEvent
from family_statistics.signals import action_event, purchase_event
from family_statistics.services import recompute, record


class Command(BaseCommand):
    help = "Recompute tenant-private statistics, enforce retention, optionally backfill reliable actors. Schedule daily."

    def add_arguments(self, parser):
        parser.add_argument("--family")
        parser.add_argument("--backfill", action="store_true")

    def handle(self, *args, **options):
        families = Family.objects.all()
        if options["family"]:
            families = families.filter(pk=options["family"])
        for family in families.iterator():
            if options["backfill"]:
                # Existing canonical Action events include proven RoutineLog actors.
                # Historical task completion actor is nullable; never use assignee.
                rows = ActionDomainEvent.objects.filter(action__family=family).select_related("action__legacy_task", "action__legacy_routine", "completion", "actor")
                for row in rows.iterator(chunk_size=500):
                    if row.event_type == "action.completed":
                        action_event(row)
                for log in RoutineLog.objects.filter(routine__family=family).select_related("routine", "done_by").iterator(chunk_size=500):
                    record(family=family, domain="routine", action="completed", entity_type="routine", entity_id=log.routine_id, occurred_at=log.done_at, actor=log.done_by, source="import", idempotency_key=f"routine-log:{log.pk}")
                for task in Task.objects.filter(family=family, completed_at__isnull=False, birthday_context__isnull=True, hidden_from_user__isnull=True).iterator(chunk_size=500):
                    key = f"task-completion:{task.pk}:{task.completed_at.isoformat()}"
                    record(family=family, domain="task", action="completed", entity_type="task", entity_id=task.pk, occurred_at=task.completed_at, actor=None, effort_minutes=task.estimate_minutes, source="import", idempotency_key=key)
                for event in ShoppingPurchaseEvent.objects.filter(family=family).iterator(chunk_size=500):
                    purchase_event(event)
            recompute(family)
        self.stdout.write(self.style.SUCCESS("Statistics rollups rebuilt; retention applied."))
