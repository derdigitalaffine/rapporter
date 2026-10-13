from difflib import SequenceMatcher
from copy import deepcopy
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from .action_views import _family_membership
from .action_projection import project_actions
from .action_schedule import normalize_schedule, parse_schedule, predict
from .models import Routine, Task, Membership
from .unified_action_models import Action, ActionCompletion, ActionCapture
from .unified_action_service import execute, mirror, resolve, payload, validate_command

ICON_CHOICES = ['tasks', 'waste', 'bed', 'dog', 'bowl-food', 'shopping', 'calendar', 'home', 'pet', 'school', 'heart', 'clock', 'water', 'broom', 'utensils', 'car', 'recycle', 'history', 'check']
ACCENT_CHOICES = ['', 'blue', 'green', 'amber', 'rose', 'violet']


def icon_suggestions(title):
    title = title.casefold()
    matches = []
    for terms, icons in [(('müll', 'tonne', 'trash', 'waste'), ['waste', 'recycle']), (('bett', 'bed'), ['bed', 'home']), (('hund', 'dog', 'fütter', 'feed'), ['dog', 'bowl-food', 'pet']), (('putz', 'clean'), ['broom', 'home']), (('essen', 'cook'), ['utensils', 'shopping'])]:
        if any(t in title for t in terms):
            matches.extend(icons)
    return list(dict.fromkeys(matches + ['tasks', 'check', 'home']))[:5]


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def action_execute(request):
    if not isinstance(request.data, dict):
        raise ValidationError('Expected an object.')
    return Response(execute(request.user, request.data.get('action_id'), request.data))


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def action_detail(request, kind, object_id):
    obj = resolve(request.user, f'{kind}:{object_id}')
    with transaction.atomic():
        type(obj).objects.select_for_update().get(pk=obj.pk)
        row = mirror(obj)
        row = Action.objects.select_for_update().get(pk=row.pk)
        if request.method == 'PATCH':
            data = request.data
            if not isinstance(data, dict) or set(data) - {'schedule', 'schedule_text', 'icon', 'accent_token', 'proposal_id', 'feedback'}:
                raise ValidationError('Unsupported action settings.')
            if 'schedule' in data or 'schedule_text' in data:
                try:
                    row.schedule = parse_schedule(data['schedule_text'], obj.family.timezone) if 'schedule_text' in data else normalize_schedule(data['schedule'], obj.family.timezone)
                except (ValueError, TypeError, AttributeError) as exc:
                    raise ValidationError({'schedule': str(exc)})
            if 'schedule' in data or 'schedule_text' in data:
                row.learning_cutoff_at = None if row.schedule.get('continue_learning', True) else (row.learning_cutoff_at or timezone.now())
            if 'icon' in data:
                if data['icon'] not in ICON_CHOICES:
                    raise ValidationError({'icon': 'Choose an approved icon.'})
                row.icon = data['icon']
                if isinstance(obj, Routine):
                    # Synchronize before the mirror signal so user choice remains stable.
                    obj.icon = row.icon
                    obj.save(update_fields=['icon', 'updated_at'])
            if 'accent_token' in data:
                if data['accent_token'] not in ACCENT_CHOICES:
                    raise ValidationError({'accent_token': 'Choose a design token.'})
                row.accent_token = data['accent_token']
            if 'feedback' in data:
                prediction = _prediction(row)
                proposal = (prediction or {}).get('suggested_schedule_change')
                if not proposal or data.get('proposal_id') != proposal['proposal_id']:
                    raise ValidationError({'proposal_id': 'Proposal is no longer current.'})
                if data['feedback'] == 'reject':
                    row.rejected_proposals = (row.rejected_proposals + [proposal['proposal_id']])[-128:]
                elif data['feedback'] == 'accept':
                    schedule = deepcopy(row.schedule)
                    weekday = proposal['proposed']['weekday']
                    segments = []
                    for segment in schedule.get('segments', []):
                        days = [d for d in segment.get('weekdays', ['MO','TU','WE','TH','FR','SA','SU']) if d != weekday]
                        if days:
                            segments.append({**segment, 'weekdays': days})
                    segments.append({'weekdays': [weekday], 'preferred_time': proposal['proposed']['preferred_time']})
                    schedule['segments'] = segments
                    row.schedule = normalize_schedule(schedule, obj.family.timezone)
                else:
                    raise ValidationError({'feedback': 'Choose accept or reject.'})
            row.save()
        from .context_models import ContextLink
        from decisions.access import visible_decisions_queryset
        ids = ContextLink.objects.filter(family=obj.family, source_type=kind, source_id=obj.id, context_type='decision', relation_key='action.context').values_list('context_id', flat=True)
        templates = list(visible_decisions_queryset(request.user, obj.family).filter(id__in=ids).values('id','question')[:20])
        return Response({'decision_templates': templates, 'id': str(row.id), 'action_id': f'{kind}:{obj.id}', 'schedule': row.schedule, 'prediction': _prediction(row), 'icon': row.icon, 'accent_token': row.accent_token, 'icon_choices': ICON_CHOICES, 'accent_choices': ACCENT_CHOICES, 'icon_suggestions': icon_suggestions(row.title), 'migration_phase': row.migration_phase})


def _prediction(row):
    if not row.schedule:
        return None
    from .action_prediction import prediction_for
    from .unified_action_models import ActionPolicy
    policy = ActionPolicy.objects.filter(family_id=row.family_id).first()
    observations = list(row.completions.filter(undone_at__isnull=True).order_by('-occurred_at').values_list('occurred_at', flat=True)[:64])
    return prediction_for(row, observations, timezone.now(), policy)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def quick_capture(request):
    family, membership, error = _family_membership(request)
    if error is not None:
        return error
    if request.method == 'GET':
        from .unified_action_models import ActionPersonalSetting
        personal = ActionPersonalSetting.objects.filter(membership=membership).first()
        if personal and not personal.capture_suggestions:
            return Response({'suggestions': [], 'suggestions_enabled': False, 'icon_suggestions': [], 'auto_merge': False})
        query = str(request.query_params.get('q', '')).strip()[:160]
        rows = project_actions(user=request.user, family=family, scope='all')
        rows = [r for r in rows if r['state'] != 'paused' and (r['kind'] == 'routine' or r['state'] not in {'done', 'done_today'} or query)]
        for row in rows:
            similarity = SequenceMatcher(None, query.casefold(), row['title'].casefold()).ratio() if query else 0
            row['capture_match'] = round(similarity, 3)
            row['capture_reason'] = 'title_match' if query else ('assigned_to_me' if (row.get('assignee') or {}).get('id') == request.user.id else 'due_now' if row['state'] in {'due', 'overdue'} else 'available')
        if query:
            rows = [r for r in rows if r['capture_match'] >= .35 or query.casefold() in r['title'].casefold()]
            rows.sort(key=lambda r: (-r['capture_match'], r['title'].casefold()))
        return Response({'suggestions': rows[:6], 'suggestions_enabled': True, 'icon_suggestions': icon_suggestions(query), 'auto_merge': False})
    data = request.data
    if not isinstance(data, dict):
        raise ValidationError('Expected an object.')
    request_id, duration, source = validate_command({**data, 'source': 'quick_capture'})
    typed_id = data.get('action_id')
    if typed_id:
        obj = resolve(request.user, typed_id)
        if obj.family_id != family.id:
            raise NotFound()
        return Response(execute(request.user, typed_id, {**data, 'source': 'quick_capture'}))
    title = data.get('title', '')
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
        raise ValidationError({'title': 'Choose a title of 1–160 characters.'})
    if 'icon' in data and data['icon'] not in ICON_CHOICES:
        raise ValidationError({'icon': 'Choose an approved icon.'})
    if data.get('create_new') is not True:
        raise ValidationError({'create_new': 'Explicitly choose to create a new action.'})
    with transaction.atomic():
        # Membership lock serializes the create+complete retry without a second object.
        Membership.objects.select_for_update().get(pk=membership.pk)
        receipt = ActionCapture.objects.filter(family=family, request_id=request_id).first()
        if receipt:
            if receipt.actor_id != request.user.id:
                raise PermissionDenied()
            return Response(payload(receipt.completion))
        routine = Routine.objects.create(family=family, name=title.strip(), icon=data.get('icon') or icon_suggestions(title)[0], reminder_enabled=False)
        row = mirror(routine)
        row.schedule = normalize_schedule({'mode': 'learning'}, family.timezone)
        row.save(update_fields=['schedule', 'updated_at'])
        result = execute(request.user, f'routine:{routine.id}', {**data, 'source': 'quick_capture'})
        completion = ActionCompletion.objects.get(pk=result['id'])
        ActionCapture.objects.create(family=family, request_id=request_id, actor=request.user, action=row, completion=completion, original_title=title.strip())
        return Response({**result, 'action_id': f'routine:{routine.id}'}, status=201)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def event_actions(request):
    from .models import FamilyEvent
    family, membership, error = _family_membership(request)
    if error is not None:
        return error
    if request.method == 'POST':
        if not isinstance(request.data, dict):
            raise ValidationError('Expected an object.')
        typed_id = request.data.get('action_id')
        obj = resolve(request.user, typed_id)
        if not isinstance(obj, FamilyEvent) or obj.family_id != family.id:
            raise NotFound()
        return Response(execute(request.user, typed_id, {**request.data, 'source': 'widget'}))
    ids = request.query_params.getlist('event')[:20]
    from uuid import UUID
    try:
        ids = [UUID(v) for v in ids]
    except ValueError:
        raise ValidationError({'event': 'Invalid event ID.'})
    rows = Action.objects.filter(family=family, legacy_event_id__in=ids)
    completions = ActionCompletion.objects.filter(action__in=rows, undone_at__isnull=True).order_by('-occurred_at')
    by_event = {}
    for completion in completions.select_related('action'):
        by_event.setdefault(str(completion.action.legacy_event_id), payload(completion))
    return Response({'completions': by_event})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def context_action(request):
    """Explicit creation/linking only; canonical Context Registry owns ACLs."""
    from .context_views import _error_response
    from .context_links import create_context_link, ContextLinkError
    family, membership, error = _family_membership(request)
    if error is not None:
        return error
    if not isinstance(request.data, dict):
        raise ValidationError('Expected an object.')
    context = request.data.get('context')
    if not isinstance(context, dict):
        raise ValidationError({'context': 'Choose a canonical context object.'})
    typed_id = request.data.get('action_id')
    created = False
    if typed_id:
        obj = resolve(request.user, typed_id)
        if obj.family_id != family.id or not isinstance(obj, (Task, Routine)):
            raise NotFound()
    else:
        title = request.data.get('title')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
            raise ValidationError({'title': 'Choose a title of 1–160 characters.'})
        if request.data.get('recurring') is True:
            obj = Routine.objects.create(family=family, name=title.strip(), reminder_enabled=False)
        else:
            obj = Task.objects.create(family=family, title=title.strip(), created_by=request.user)
        created = True
    kind = 'task' if isinstance(obj, Task) else 'routine'
    try:
        link, _ = create_context_link(user=request.user, family=family, source_type=kind, source_id=obj.id,
            context_type=context.get('type'), context_id=context.get('id'), relation_key='action.context')
    except ContextLinkError as exc:
        transaction.set_rollback(True)
        return _error_response(exc)
    row = mirror(obj)
    if 'schedule' in request.data:
        try:
            row.schedule = normalize_schedule(request.data['schedule'], family.timezone)
        except (ValueError, TypeError) as exc:
            raise ValidationError({'schedule': str(exc)})
        row.save(update_fields=['schedule', 'updated_at'])
    return Response({'action_id': f'{kind}:{obj.id}', 'link_id': str(link.id), 'created': created}, status=201 if created else 200)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def decision_round(request):
    from decisions.access import visible_decisions_queryset
    from decisions.context import _decision_can_link
    from decisions.models import Decision, DecisionOption
    from .context_models import ContextLink
    from .context_links import create_context_link
    from .unified_action_models import ActionDecisionRound
    from uuid import UUID
    data = request.data
    if not isinstance(data, dict):
        raise ValidationError('Expected an object.')
    request_id, _, _ = validate_command(data)
    obj = resolve(request.user, data.get('action_id'))
    if not isinstance(obj, (Task, Routine)):
        raise ValidationError({'action_id': 'Choose an executable task or routine.'})
    type(obj).objects.select_for_update().get(pk=obj.pk)
    row = mirror(obj)
    row = Action.objects.select_for_update().get(pk=row.pk)
    receipt = row.decision_rounds.filter(request_id=request_id).first()
    if receipt:
        if receipt.actor_id != request.user.id:
            raise PermissionDenied()
        return Response({'decision_id': str(receipt.decision_id), 'deep_link': f'/?page=decisions&decision={receipt.decision_id}'})
    try:
        template_id = UUID(str(data.get('template_id')))
    except ValueError:
        raise ValidationError({'template_id': 'Invalid template ID.'})
    template = visible_decisions_queryset(request.user, obj.family).filter(pk=template_id).first()
    if not template:
        raise NotFound()
    if not _decision_can_link(request.user, template):
        raise PermissionDenied()
    kind = 'task' if isinstance(obj, Task) else 'routine'
    if not ContextLink.objects.filter(family=obj.family, source_type=kind, source_id=obj.id, context_type='decision', context_id=template.id, relation_key='action.context').exists():
        raise ValidationError({'template_id': 'Link the definition to this action first.'})
    options = list(template.options.order_by('position'))
    if not 2 <= len(options) <= 20:
        raise ValidationError({'template_id': 'Template needs 2–20 options.'})
    new = Decision.objects.create(family=obj.family, question=template.question, mode=template.mode, anonymous=template.anonymous, created_by=request.user, context_bound=template.context_bound)
    DecisionOption.objects.bulk_create([DecisionOption(decision=new, label=option.label, position=index) for index, option in enumerate(options)])
    # Keep context-bound definitions context-bound; copy references, never votes.
    for link in ContextLink.objects.filter(family=obj.family, source_type='decision', source_id=template.id, relation_key='decision.context'):
        create_context_link(user=request.user, family=obj.family, source_type='decision', source_id=new.id,
            context_type=link.context_type, context_id=link.context_id, relation_key='decision.context')
    create_context_link(user=request.user, family=obj.family, source_type=kind, source_id=obj.id, context_type='decision', context_id=new.id, relation_key='action.context')
    ActionDecisionRound.objects.create(action=row, template=template, decision=new, request_id=request_id, actor=request.user)
    return Response({'decision_id': str(new.id), 'deep_link': f'/?page=decisions&decision={new.id}'}, status=201)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def completion_duration(request, completion_id):
    completion = ActionCompletion.objects.select_related('action').filter(pk=completion_id, action__family__memberships__user=request.user, action__family__status='active', undone_at__isnull=True).first()
    if not completion:
        raise NotFound()
    row = completion.action
    typed_id = f'task:{row.legacy_task_id}' if row.legacy_task_id else f'routine:{row.legacy_routine_id}' if row.legacy_routine_id else f'event:{row.legacy_event_id}'
    resolve(request.user, typed_id)
    if completion.actor_id != request.user.id:
        raise PermissionDenied()
    if not isinstance(request.data, dict):
        raise ValidationError('Expected an object.')
    duration = request.data.get('duration_minutes')
    _, duration, _ = validate_command({'request_id': str(__import__('uuid').uuid4()), 'duration_minutes': duration})
    completion.duration_minutes = duration
    completion.save(update_fields=['duration_minutes', 'updated_at'])
    return Response(payload(completion))


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def action_settings(request):
    from .unified_action_models import ActionPolicy, ActionPersonalSetting
    family, membership, error = _family_membership(request)
    if error is not None:
        return error
    with transaction.atomic():
        Membership.objects.select_for_update().get(pk=membership.pk)
        personal, _ = ActionPersonalSetting.objects.get_or_create(membership=membership)
        policy, _ = ActionPolicy.objects.get_or_create(family=family)
        if request.method == 'PATCH':
            data = request.data
            if not isinstance(data, dict) or set(data)-{'capture_suggestions', 'personal_calendar_aware', 'adaptive_enabled', 'calendar_aware', 'learning_history_days'}:
                raise ValidationError('Unsupported settings.')
            if set(data)&{'adaptive_enabled','calendar_aware','learning_history_days'} and membership.role not in {'owner','adult'}:
                raise PermissionDenied()
            for key, value in data.items():
                if key == 'learning_history_days':
                    if isinstance(value, bool) or not isinstance(value, int) or not 7 <= value <= 3650:
                        raise ValidationError({key:'Choose 7–3650 days.'})
                elif not isinstance(value, bool):
                    raise ValidationError({key:'Expected boolean.'})
                if key == 'capture_suggestions': personal.capture_suggestions = value
                elif key == 'personal_calendar_aware': personal.calendar_aware = value
                else: setattr(policy, key, value)
            personal.save()
            policy.save()
        return Response({'capture_suggestions': personal.capture_suggestions, 'personal_calendar_aware': personal.calendar_aware, 'adaptive_enabled': policy.adaptive_enabled, 'calendar_aware': policy.calendar_aware, 'learning_history_days':policy.learning_history_days, 'can_manage_family': membership.role in {'owner','adult'}})
