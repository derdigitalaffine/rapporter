"""Legacy-authoritative dual write, completion commands and repeatable repair."""
from uuid import UUID
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from .models import Task, TaskList, Routine, RoutineLog, Membership, Family, FamilyEvent
from .unified_action_models import Action, ActionCompletion, ActionCommand


def mirror(obj):
    if isinstance(obj, FamilyEvent):
        return Action.objects.update_or_create(legacy_event=obj, defaults={'family_id':obj.family_id, 'title':obj.title, 'kind_hint':'event', 'due_at':obj.starts_at, 'icon':'waste', 'source':'external_event'})[0]
    task = isinstance(obj, Task)
    defaults = {'family_id': obj.family_id, 'title': obj.title if task else obj.name,
                'kind_hint': 'task' if task else 'routine',
                'state': ('done' if obj.completed_at else 'open') if task else ('open' if obj.active else 'paused')}
    if task:
        defaults.update(assignee_id=obj.assignee_id, created_by_id=obj.created_by_id,
                        due_at=obj.due_at, priority=obj.priority, estimate_minutes=obj.estimate_minutes, source=obj.source)
    else:
        defaults['icon'] = obj.icon
    row, _ = Action.objects.update_or_create(**{'legacy_task' if task else 'legacy_routine': obj}, defaults=defaults)
    return row


def observe_task(obj, previous=None):
    row = mirror(obj)
    old = (previous or {}).get('completed_at')
    if obj.completed_at and old != obj.completed_at:
        from .request_context import current_actor
        ActionCompletion.objects.get_or_create(action=row, occurred_at=obj.completed_at, legacy_log=None,
            defaults={'actor': current_actor(), 'source': 'automation' if obj.source.startswith('rule:') else 'ui'})
    elif old and not obj.completed_at:
        row.completions.filter(undone_at__isnull=True).update(undone_at=timezone.now())
    return row


def observe_log(log):
    row = mirror(log.routine)
    completion, _ = ActionCompletion.objects.get_or_create(legacy_log=log,
        defaults={'action': row, 'actor': log.done_by, 'occurred_at': log.done_at, 'request_id': log.request_id})
    return completion


def resolve(user, typed_id):
    try:
        kind, raw = str(typed_id).split(':', 1)
        object_id = UUID(raw)
    except (ValueError, TypeError):
        raise ValidationError({'action_id': 'Invalid action ID.'})
    model = {'task': Task, 'routine': Routine, 'event': FamilyEvent}.get(kind)
    if model is None:
        raise ValidationError({'action_id': 'Invalid action kind.'})
    rows = model.objects.filter(pk=object_id, family__status=Family.Status.ACTIVE, family__memberships__user=user)
    if kind == 'event':
        rows = rows.filter(type__startswith='waste.')
    if kind == 'task':
        rows = rows.exclude(hidden_from_user=user)
    obj = rows.first()
    if obj is None:
        raise NotFound()
    return obj


def payload(completion):
    return {'id': str(completion.id), 'action': str(completion.action_id), 'actor': completion.actor_id,
            'occurred_at': completion.occurred_at, 'duration_minutes': completion.duration_minutes,
            'source': completion.source, 'undone_at': completion.undone_at,
            'legacy_log': str(completion.legacy_log_id) if completion.legacy_log_id else None}


def validate_command(data):
    try:
        request_id = UUID(str(data.get('request_id')))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({'request_id': 'A UUID idempotency key is required.'})
    duration = data.get('duration_minutes')
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int) or not 0 <= duration <= 10080):
        raise ValidationError({'duration_minutes': 'Choose 0–10080 minutes.'})
    source = data.get('source', 'ui')
    if not isinstance(source, str) or source not in {'ui', 'quick_capture', 'widget', 'automation', 'import'}:
        raise ValidationError({'source': 'Invalid source.'})
    return request_id, duration, source


@transaction.atomic
def execute(user, typed_id, data):
    request_id, duration, source = validate_command(data)
    operation = data.get('operation', 'complete')
    if not isinstance(operation, str) or operation not in {'complete', 'reopen', 'undo'}:
        raise ValidationError({'operation': 'Invalid operation.'})
    obj = resolve(user, typed_id)
    # Use the same lock order as legacy workflow writers: list, task, action.
    if isinstance(obj, Task) and obj.task_list_id:
        TaskList.objects.select_for_update().get(pk=obj.task_list_id)
    obj = type(obj).objects.select_for_update().get(pk=obj.pk)
    row = mirror(obj)
    row = Action.objects.select_for_update().get(pk=row.pk)
    receipt = row.commands.filter(request_id=request_id).first()
    if receipt:
        if receipt.actor_id != user.id:
            raise PermissionDenied()
        if receipt.operation != operation:
            raise ValidationError({'request_id': 'Key already used for another operation.'})
        return payload(receipt.completion) if receipt.completion else {'undone': True}
    completion = None
    repeating_task = isinstance(obj, Task) and row.schedule.get('recurrence', {}).get('frequency') in {'daily','weekly','monthly','yearly'}
    already_complete = isinstance(obj, Task) and bool(obj.completed_at) and not repeating_task
    if operation == 'complete':
        if isinstance(obj, FamilyEvent):
            completion = row.completions.filter(undone_at__isnull=True).order_by('-occurred_at').first()
            if completion is None:
                completion = ActionCompletion.objects.create(action=row, actor=user, occurred_at=timezone.now(), request_id=request_id, duration_minutes=duration, source=source)
        elif isinstance(obj, Routine):
            if not obj.active:
                raise ValidationError({'action': 'Reactivate this routine first.'})
            log = RoutineLog.objects.create(routine=obj, done_by=user, done_at=timezone.now(), request_id=request_id)
            completion = observe_log(log)
        elif obj.completed_at and not repeating_task:
            completion = row.completions.filter(undone_at__isnull=True).order_by('-occurred_at').first()
            if completion is None:
                completion = ActionCompletion.objects.create(action=row, actor=None, occurred_at=obj.completed_at, source='import')
        else:
            obj.completed_at = timezone.now()
            obj.save(update_fields=['completed_at', 'updated_at'])
            completion = row.completions.filter(undone_at__isnull=True).order_by('-occurred_at').first()
        # Do not change attribution/duration when another command already completed a task.
        if completion and not already_complete and (isinstance(obj, (Routine, FamilyEvent)) or completion.actor_id in {None, user.id}):
            if not completion.request_id:
                completion.actor = user
                completion.request_id = request_id
                completion.duration_minutes = duration
                completion.source = source
                completion.save()
            elif isinstance(obj, Routine):
                completion.duration_minutes = duration
                completion.source = source
                completion.save(update_fields=['duration_minutes', 'source', 'updated_at'])
    else:
        if operation == 'undo':
            try:
                completion = row.completions.get(pk=UUID(str(data.get('completion_id'))))
            except (ActionCompletion.DoesNotExist, ValueError, TypeError):
                raise NotFound()
            if completion.actor_id != user.id and not Membership.objects.filter(family=obj.family, user=user, role__in=['owner', 'adult']).exists():
                raise PermissionDenied()
        elif isinstance(obj, (Routine, FamilyEvent)):
            raise ValidationError({'operation': 'Use undo with a completion ID.'})
        if isinstance(obj, Task):
            # Undo of an older cycle must not reopen a newer completion.
            if operation == 'reopen' or (completion and obj.completed_at == completion.occurred_at):
                obj.completed_at = None
                obj.save(update_fields=['completed_at', 'updated_at'])
        elif isinstance(obj, Routine) and completion and completion.legacy_log_id:
            completion.legacy_log.delete()
            completion.legacy_log = None
        if completion and not completion.undone_at:
            completion.undone_at = timezone.now()
            completion.save(update_fields=['undone_at', 'updated_at'])
    ActionCommand.objects.create(action=row, request_id=request_id, actor=user, operation=operation, completion=completion)
    return payload(completion) if completion else {'undone': True}
