from copy import deepcopy

from django.db import transaction

from .models import Membership, Routine, Task, TaskList
from .predictions import routine_prediction
from .routine_task_migration_models import RoutineTaskMigration
from .unified_action_models import Action, ActionCompletion


SOURCE_PREFIX = "routine-migration:"


def migration_source(routine_id):
    return f"{SOURCE_PREFIX}{routine_id}"


def _stamp(value):
    return value.isoformat() if value else None


def routine_snapshot(routine, *, action=None):
    logs = routine.logs.select_related("done_by").order_by("done_at", "id")
    reminder_states = routine.reminder_states.select_related("membership").order_by("membership_id")
    return {
        "version": "legacy-routine-v1",
        "routine": {
            "id": str(routine.id),
            "name": routine.name,
            "icon": routine.icon,
            "active": routine.active,
            "suggested_interval_days": routine.suggested_interval_days,
            "target_count": routine.target_count,
            "target_period_days": routine.target_period_days,
            "reminder_enabled": routine.reminder_enabled,
            "created_at": _stamp(routine.created_at),
            "updated_at": _stamp(routine.updated_at),
        },
        "reminder_states": [
            {
                "membership_id": str(state.membership_id),
                "snoozed_until": _stamp(state.snoozed_until),
                "last_sent_at": _stamp(state.last_sent_at),
                "last_cycle_at": _stamp(state.last_cycle_at),
            }
            for state in reminder_states
        ],
        "logs": [
            {
                "id": str(log.id),
                "done_at": _stamp(log.done_at),
                "done_by": log.done_by_id,
                "note": log.note,
                "request_id": str(log.request_id) if log.request_id else None,
                "created_at": _stamp(log.created_at),
            }
            for log in logs
        ],
        "action": {
            "schedule": deepcopy(action.schedule) if action else {},
            "accent_token": action.accent_token if action else "",
            "rejected_proposals": deepcopy(action.rejected_proposals) if action else [],
            "learning_cutoff_at": _stamp(action.learning_cutoff_at) if action else None,
        },
    }


def _default_task_list(family):
    return TaskList.objects.get_or_create(
        family=family,
        name="Allgemein",
        defaults={"icon": "list-check"},
    )[0]


def migration_for_routine(routine):
    return RoutineTaskMigration.objects.select_related("task", "routine").filter(routine=routine).first()


def migration_for_task(task):
    return RoutineTaskMigration.objects.select_related("task", "routine").filter(task=task).first()


def sync_migrated_task_from_routine(routine):
    """Keep the canonical Task's next due/status aligned with the compatibility backing.

    Routine reminder delivery and the legacy prediction algorithm continue to consume
    RoutineLog rows; every migrated completion therefore updates both representations.
    """
    migration = migration_for_routine(routine)
    if migration is None:
        return None
    prediction = routine_prediction(routine)
    due_at = prediction.get("expected_at") if routine.active else None
    Task.objects.filter(pk=migration.task_id).update(title=routine.name, due_at=due_at)
    row = Action.objects.filter(legacy_task_id=migration.task_id).first()
    if row:
        row.title = routine.name
        row.due_at = due_at
        row.state = "open" if routine.active else "paused"
        row.save(update_fields=["title", "due_at", "state", "updated_at"])
    return migration.task


@transaction.atomic
def migrate_routine_to_task(*, routine, user):
    routine = (
        Routine.objects.select_for_update()
        .select_related("family")
        .prefetch_related("logs__done_by", "reminder_states__membership")
        .get(pk=routine.pk)
    )
    if not Membership.objects.filter(family=routine.family, user=user).exists():
        raise PermissionError("Routine is not available to this user.")

    existing = migration_for_routine(routine)
    if existing:
        return existing.task, False

    # Materialize every legacy completion before the handover so the canonical
    # completion stream remains complete and can be rehomed atomically below.
    from .unified_action_service import mirror, observe_log, domain_event

    old_action = mirror(routine)
    for log in routine.logs.all():
        observe_log(log)

    source = migration_source(routine.id)
    task = Task.objects.filter(family=routine.family, source=source).first()
    if task is None:
        task = Task.objects.create(
            family=routine.family,
            task_list=_default_task_list(routine.family),
            title=routine.name,
            created_by=user,
            source=source,
        )

    snapshot = routine_snapshot(routine, action=old_action)
    migration = RoutineTaskMigration.objects.create(
        family=routine.family,
        routine=routine,
        task=task,
        snapshot=snapshot,
        created_by=user,
    )

    new_action = mirror(task)
    new_action.title = routine.name
    new_action.icon = old_action.icon or routine.icon
    new_action.accent_token = old_action.accent_token
    new_action.schedule = deepcopy(old_action.schedule)
    new_action.rejected_proposals = deepcopy(old_action.rejected_proposals)
    new_action.learning_cutoff_at = old_action.learning_cutoff_at
    new_action.state = "open" if routine.active else "paused"
    new_action.migration_phase = "canonical"
    new_action.save(update_fields=[
        "title", "icon", "accent_token", "schedule", "rejected_proposals",
        "learning_cutoff_at", "state", "migration_phase", "updated_at",
    ])

    ActionCompletion.objects.filter(action=old_action).update(action=new_action)
    old_action.state = "archived"
    old_action.migration_phase = "retired"
    old_action.save(update_fields=["state", "migration_phase", "updated_at"])

    sync_migrated_task_from_routine(routine)
    task.refresh_from_db()
    domain_event(new_action, "action.migrated", f"routine-migration:{routine.id}", actor=user)
    return task, True
