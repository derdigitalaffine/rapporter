from django.core.exceptions import ValidationError
from django.db import transaction

from .models import FamilyEvent
from .scheduling_models import SchedulingDependency, SchedulingMaterialization
from .unified_action_models import Action


ALLOWED_FIELDS = {"scheduled_for", "title", "location", "description", "participants", "notes", "priority"}


def _snapshot_field(row, field, snapshot):
    """Snapshot the current canonical output value; return a detached schedule time when relevant."""
    if row.output_type == SchedulingDependency.OutputType.EVENT:
        event = FamilyEvent.objects.filter(family=row.family, id=row.output_id).first()
        if event is None:
            return None
        payload = event.payload if isinstance(event.payload, dict) else {}
        if field == "scheduled_for":
            value = event.starts_at or row.scheduled_for
            snapshot[field] = value.isoformat()
            return value
        if field == "title":
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
            return None
        if field == "scheduled_for":
            value = task.due_at or row.scheduled_for
            snapshot[field] = value.isoformat()
            return value
        if field == "title":
            snapshot[field] = task.title
        elif field == "notes":
            snapshot[field] = task.notes
        elif field == "priority":
            snapshot[field] = task.priority
    return None


@transaction.atomic
def detach_materialization_fields(row, fields):
    if not isinstance(fields, list) or any(field not in ALLOWED_FIELDS for field in fields):
        raise ValidationError({"fields": "Unsupported detached fields."})
    row = SchedulingMaterialization.objects.select_for_update().get(pk=row.pk)
    fields = sorted(set(fields))
    snapshot = dict(row.projected_payload or {})
    detached_schedule = None
    for field in fields:
        value = _snapshot_field(row, field, snapshot)
        if field == "scheduled_for" and value is not None:
            detached_schedule = value
    provenance = dict(row.provenance or {})
    provenance["detached_fields"] = fields
    row.projected_payload = snapshot
    row.provenance = provenance
    update_fields = ["projected_payload", "provenance", "updated_at"]
    if detached_schedule is not None:
        row.scheduled_for = detached_schedule
        update_fields.append("scheduled_for")
    row.save(update_fields=update_fields)
    return row
