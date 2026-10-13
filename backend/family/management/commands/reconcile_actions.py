from django.core.management.base import BaseCommand
from django.db import transaction
from family.models import Task, Routine
from family.unified_action_service import mirror, observe_log, observe_task
from family.unified_action_models import Action

class Command(BaseCommand):
    help = 'Repeatable additive legacy Action backfill and shadow parity report; no legacy writes.'
    def add_arguments(self, parser):
        parser.add_argument('--check', action='store_true', help='Report mirror drift without repairing it.')
    def handle(self, *args, **options):
        drift = checked = 0
        for model, key, field in [(Task, 'legacy_task', 'title'), (Routine, 'legacy_routine', 'name')]:
            for obj in model.objects.all().iterator(chunk_size=250):
                checked += 1
                row = Action.objects.filter(**{key: obj}).first()
                state = ('done' if obj.completed_at else 'open') if model is Task else ('open' if obj.active else 'paused')
                differs = row is None or row.family_id != obj.family_id or row.title != getattr(obj, field) or row.state != state
                if model is Task and row is not None:
                    differs = differs or any(getattr(row, name) != getattr(obj, name) for name in ['assignee_id','created_by_id','due_at','priority','estimate_minutes','source'])
                if differs:
                    drift += 1
                if not options['check']:
                    with transaction.atomic():
                        obj = model.objects.select_for_update().get(pk=obj.pk)
                        if model is Task:
                            observe_task(obj, {'completed_at': obj.completed_at})
                            if obj.completed_at:
                                from family.unified_action_models import ActionCompletion
                                row = mirror(obj)
                                ActionCompletion.objects.get_or_create(action=row, occurred_at=obj.completed_at, legacy_log=None, defaults={'source': 'import'})
                        else:
                            mirror(obj)
                            for log in obj.logs.all().iterator(chunk_size=250):
                                observe_log(log)
        self.stdout.write(f'actions-shadow-v1 checked={checked} drift={drift} repaired={not options["check"]}')
