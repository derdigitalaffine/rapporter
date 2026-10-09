"""Optional list workflows. List locks serialize position and completion changes."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Task, TaskList, TaskStatusEvent, TaskWorkflowColumn
from .request_context import current_actor


def configure_workflow(task_list, enabled):
    with transaction.atomic():
        task_list = TaskList.objects.select_for_update().get(pk=task_list.pk)
        columns = list(task_list.workflow_columns.filter(archived=False))
        if enabled and not columns:
            names = ["Offen", "In Arbeit", "Erledigt"] if not task_list.family.locale.startswith("en") else ["Open", "In progress", "Done"]
            columns = [TaskWorkflowColumn.objects.create(task_list=task_list, name=name, key=kind, position=i, kind=kind, is_terminal=kind=="done") for i, (name, kind) in enumerate(zip(names, ["open", "active", "done"]))]
        task_list.workflow_enabled = enabled
        task_list.save(update_fields=["workflow_enabled", "updated_at"])
        if enabled:
            for task in task_list.tasks.order_by("created_at"):
                task.save()
        return task_list


def prepare_task(task):
    previous = Task.objects.filter(pk=task.pk).values("workflow_column_id", "completed_at", "task_list_id").first()
    if not task.task_list_id:
        task.workflow_column = None
        task.workflow_position = None
        return previous
    task_list = TaskList.objects.select_for_update().get(pk=task.task_list_id)
    previous = Task.objects.filter(pk=task.pk).values("workflow_column_id", "completed_at", "task_list_id").first()
    if task_list.family_id != task.family_id:
        raise ValidationError({"task_list": "Task list belongs to another family."})
    if not task_list.workflow_enabled:
        task.workflow_column = None
        task.workflow_position = None
        return previous
    columns = list(task_list.workflow_columns.filter(archived=False))
    column = next((row for row in columns if row.id == task.workflow_column_id), None)
    if task.workflow_column_id and not column and previous and previous["task_list_id"] == task.task_list_id:
        raise ValidationError({"workflow_column": "Invalid workflow column."})
    column_changed = previous and previous["workflow_column_id"] != task.workflow_column_id and column
    completion_changed = previous and previous["completed_at"] != task.completed_at
    if not column or (completion_changed and not column_changed):
        terminal = bool(task.completed_at)
        target = None
        if not terminal and previous:
            event = task.status_events.filter(to_column__is_terminal=False, to_column__archived=False, to_column__task_list_id=task.task_list_id).select_related("to_column").first()
            target = event.to_column if event else None
        column = target or next((row for row in columns if row.is_terminal == terminal), None)
    if not column:
        raise ValidationError({"workflow_column": "Workflow requires open and done columns."})
    task.workflow_column = column
    task.completed_at = (task.completed_at or timezone.now()) if column.is_terminal else None
    if task.workflow_position is None or not previous or previous["workflow_column_id"] != column.id:
        last = Task.objects.filter(workflow_column=column).exclude(pk=task.pk).aggregate(last=Max("workflow_position"))["last"] or Decimal(0)
        task.workflow_position = last + 1024
    return previous


def record_status(task, previous):
    old = previous["workflow_column_id"] if previous else None
    if old == task.workflow_column_id:
        return
    actor = current_actor() or (task.created_by if not previous else None)
    TaskStatusEvent.objects.create(task=task, family=task.family, from_column_id=old, to_column_id=task.workflow_column_id, changed_by=actor, source="automation" if str(task.source).startswith("rule:") else "api")
    if task.assignee_id and actor and task.workflow_column_id and not task.birthday_context:
        from .domain_notifications import notify_domain_event
        transaction.on_commit(lambda: notify_domain_event(task.family, "task.status_changed", actor=actor, target_users=[task.assignee_id], context={"item": task.title, "status": task.workflow_column.name, "task_id": task.id, "list_id": task.task_list_id}))


@transaction.atomic
def move_task(task, column, before_task_id=None):
    task_list = TaskList.objects.select_for_update().get(pk=task.task_list_id)
    task.refresh_from_db()
    if not task_list.workflow_enabled or column.task_list_id != task_list.id or column.archived:
        raise ValidationError({"column_id": "Column must belong to this active workflow."})
    rows = list(Task.objects.filter(workflow_column=column).exclude(pk=task.pk).order_by("workflow_position", "created_at", "id"))
    if before_task_id:
        index = next((i for i, row in enumerate(rows) if str(row.id)==str(before_task_id)), None)
        if index is None:
            raise ValidationError({"before_task_id": "Target must be another task in this column."})
    else:
        index = len(rows)
    low = rows[index-1].workflow_position if index else Decimal(0)
    high = rows[index].workflow_position if index<len(rows) else low+2048
    if high-low <= Decimal("0.0000000002"):
        for i, row in enumerate(rows):
            row.workflow_position = Decimal((i+1)*1024)
        Task.objects.bulk_update(rows, ["workflow_position"])
        low = rows[index-1].workflow_position if index else Decimal(0)
        high = rows[index].workflow_position if index<len(rows) else low+2048
    task.workflow_column = column
    task.save()
    task.workflow_position = (low+high)/2
    Task.objects.filter(pk=task.pk).update(workflow_position=task.workflow_position)
    return task
