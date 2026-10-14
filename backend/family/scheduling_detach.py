from django.core.exceptions import ValidationError
from django.db import transaction

from .models import FamilyEvent
from .scheduling_models import SchedulingDependency, SchedulingMaterialization
from .unified_action_models import Action


ALLOWED_FIELDS = {"scheduled_for", "title", "location", "description", "participants", "notes", "priority"}


def _snapshot_field(row, field, snapshot):
    if row.output_type == SchedulingDependency.OutputType.EVENT:
        event = FamilyEvent.objects.filter(family=row.family, id=row.output_id).first()
        if event is None:
            return
        payload = event.payload if isinstance(event.payload, dict) else {}
        if field == "scheduled_for":
            snapshot[field] = event.starts_at.isoformat() if event.starts_at else row.scheduled_for.isoformat()
        elif field == "title":
            snapshot[field] = event.title
        elif field == "location":
            snapshot[field] = payload.get("location", "")
        elif field == "description":
            snapshot[field] = payload.get("description", "")
        elif field == "participants":
            snapshot["participant_ids"] = [str(value) for value in event.participants.values_list("id", flat=True)]
    elif row.output_type == SchedulingDependency.OutputType.ACTION:
        action = Action.objects.filter(family=row.family, id=row.output_id).select_related("legacy_task").first()
        task = action.legacy_task if action and action.legacy_task_id else None
        if task is None:
            return
        if field == "scheduled_for":
            snapshot[field] = task.due_at.isoformat() if task.due_at else row.scheduled_for.isoformat()
        elif field == "title":
            snapshot[field] = task.title
        elif field == "notes":
            snapshot[field] = task.notes
        elif field == "priority":
            snapshot[field] = task.priority


@transaction.atomic
def detach_materialization_fields(row, fields):
    if not isinstance(fields, list) or any(field not in ALLOWED_FIELDS for field in fields):
        raise ValidationError({"fields": "Unsupported detached fields."})
    row = SchedulingMaterialization.objects.select_for_update().get(pk=row.pk)
    fields = sorted(set(fields))
    snapshot = dict(row.projected_payload or {})
    for field in fields:
        _snapshot_field(row, field, snapshot)
    provenance = dict(row.provenance or {})
    provenance["detached_fields"] = fields
    row.projected_payload = snapshot
    row.provenance = provenance
    row.save(update_fields=["projected_payload", "provenance", "updated_at"])
    return row
