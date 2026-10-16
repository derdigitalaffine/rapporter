"""Authorized sync adapter over canonical viewsets/serializers/domain commands."""
import hashlib
import json
from datetime import timedelta
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIRequestFactory, force_authenticate

from .models import Family, FamilyEvent, Membership
from .sync_models import ProcessedMutation, SyncJournal, SyncSequence
from .sync_tracking import sync_lock

SNAPSHOT_KEYS = {'shopping_list': 'shopping_lists', 'shopping_item': 'shopping_items',
                 'task_list': 'task_lists', 'task': 'tasks', 'event': 'events'}


def view_for(kind, request, family, action='list', data=None):
    from .views import TaskListViewSet, TaskViewSet
    from .shopping_access_views import ShoppingListViewSet, ShoppingItemViewSet
    from .calendar_views import FamilyEventViewSet
    registry = {'shopping_list': ShoppingListViewSet, 'shopping_item': ShoppingItemViewSet,
                'task_list': TaskListViewSet, 'task': TaskViewSet, 'event': FamilyEventViewSet}
    if kind not in registry:
        raise ValidationError({'entity_type': 'Unsupported sync entity.'})
    view = registry[kind]()
    raw = APIRequestFactory().post(f'/api/sync/?family={family.pk}', data or {}, format='json')
    force_authenticate(raw, user=request.user, token=request.auth)
    view.action_map = {'post': action}
    view.args = ()
    view.kwargs = {}
    view.format_kwarg = None
    view.request = view.initialize_request(raw)
    view.action = action
    view.check_permissions(view.request)
    return view


def visible_queryset(view, kind, family):
    lookup = 'shopping_list__family_id' if kind == 'shopping_item' else 'family_id'
    return view.filter_queryset(view.get_queryset()).filter(**{lookup: family.pk})


def serialize(view, obj, kind):
    row = dict(view.get_serializer(obj).data)
    # Normalize the domain store; never embed private child entities in a parent.
    if kind == 'shopping_list':
        row.pop('items', None)
        access = row.get('access') or {}
        if access:
            row['visibility'] = access.get('visibility')
            for key in ['visible_members', 'responsible_members']:
                row[key] = [str(member['id']) for member in access.get(key, [])]
            if 'audience_group' in access:
                row['audience_group'] = access['audience_group']
    row['version'] = obj.version
    if kind == 'event':
        row['read_only'] = bool(obj.source_id or obj.external_id or obj.type != 'calendar.event')
    return json.loads(JSONRenderer().render(row))


def conflict(result, obj, view, kind, fields, local):
    row = serialize(view, obj, kind) if obj else None
    return {**result, 'status': 'conflict', 'server_version': obj.version if obj else None,
            'server_data': row, 'conflicts': {key: {'client': local.get(key), 'server': row.get(key) if row else None} for key in fields}}


def apply_mutation(request, family, mutation):
    if not isinstance(mutation, dict):
        return {'mutation_id': None, 'status': 'rejected', 'code': 'invalid_mutation'}
    result = {'mutation_id': mutation.get('mutation_id')}
    try:
        mutation_id = UUID(str(mutation.get('mutation_id')))
        entity_id = UUID(str(mutation.get('entity_id')))
        kind = mutation.get('entity_type')
        op = mutation.get('operation')
        result.update(entity_type=kind, entity_id=str(entity_id))
        fingerprint = hashlib.sha256(json.dumps(mutation, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        with sync_lock():
            previous = ProcessedMutation.objects.filter(family=family, actor=request.user, mutation_id=mutation_id).first()
            if previous:
                if previous.fingerprint != fingerprint:
                    return {**result, 'status': 'rejected', 'code': 'idempotency_key_reused'}
                return {**{k: v for k, v in previous.result.items() if k != 'data'}, 'status': 'already_applied'}
            if op not in {'create', 'update', 'delete', 'command'}:
                raise ValidationError({'operation': 'Unsupported operation.'})
            view = view_for(kind, request, family, op)
            queryset = visible_queryset(view, kind, family)
            obj = queryset.filter(pk=entity_id).first()
            if op == 'create':
                # Never disclose a guessed existing/hidden/cross-family UUID.
                if view.queryset.model.objects.filter(pk=entity_id).exists() or SyncJournal.objects.filter(entity_type=kind, entity_id=entity_id).exists():
                    return {**result, 'status': 'rejected', 'code': 'id_unavailable'}
            elif obj is None:
                # Deleted entities and permission revocation both keep local work in
                # the conflict store without exposing hidden server-side contents.
                return conflict(result, None, view, kind, ['__deleted_or_unavailable__'], {})
            else:
                view.check_object_permissions(view.request, obj)
                base = mutation.get('base_version')
                if type(base) is not int or base < 1 or base > obj.version:
                    raise ValidationError({'base_version': 'A valid existing version is required.'})
                if kind == 'event' and (obj.source_id or obj.external_id or obj.type != 'calendar.event'):
                    return {**result, 'status': 'rejected', 'code': 'read_only_source'}
                if base != obj.version:
                    local = mutation.get('changes', {}) if op == 'update' else {}
                    history = list(SyncJournal.objects.filter(family=family, entity_type=kind, entity_id=entity_id, version__gt=base).values('version', 'changed_fields'))
                    # Missing retained history cannot prove a disjoint merge.
                    versions = {row['version'] for row in history}
                    complete = len(versions) == obj.version - base
                    changed = {field for row in history for field in row['changed_fields']}
                    overlap = set(local) & changed
                    if op != 'update' or not complete:
                        return conflict(result, obj, view, kind, ['__version__'], local)
                    canonical = serialize(view, obj, kind)
                    overlap = {key for key in overlap if local[key] != canonical.get(key)}
                    if overlap:
                        return conflict(result, obj, view, kind, overlap, local)
            if op in {'create', 'update'}:
                data = mutation.get('data' if op == 'create' else 'changes')
                if not isinstance(data, dict):
                    raise ValidationError({'data': 'Expected an object.'})
                data = dict(data)
                if kind != 'shopping_item':
                    if 'family' in data and str(data['family']) != str(family.pk):
                        raise ValidationError({'family': 'Family is immutable.'})
                    data['family'] = str(family.pk)
                if kind == 'shopping_item' and 'shopping_list' in data:
                    from .models import ShoppingList
                    if not ShoppingList.objects.filter(pk=data['shopping_list'], family=family).exists():
                        raise ValidationError({'shopping_list': 'List is outside the requested family.'})
                if kind == 'event' and op == 'create':
                    if data.get('type', 'calendar.event') != 'calendar.event' or data.get('source'):
                        raise ValidationError({'type': 'Only native calendar events can be created.'})
                    data['type'] = 'calendar.event'
                access_keys = {'visibility', 'visible_members', 'responsible_members', 'audience_group'} if kind == 'shopping_list' else set()
                access_data = {key: data.pop(key) for key in access_keys if key in data}
                serializer = view.get_serializer(obj, data=data, partial=op == 'update')
                allowed = {name for name, field in serializer.fields.items() if not field.read_only} - {'id', 'version', 'hidden_from_user', 'birthday_context'}
                if kind == 'event':
                    allowed.discard('external_id')
                unknown = set(data) - allowed
                if unknown:
                    raise ValidationError({key: 'Field is not writable through sync.' for key in sorted(unknown)})
                serializer.is_valid(raise_exception=True)
                if op == 'create':
                    serializer.validated_data['id'] = entity_id
                    if kind == 'shopping_item' and serializer.validated_data.get('checked'):
                        serializer.validated_data['checked_at'] = timezone.now()
                    view.perform_create(serializer)
                else:
                    view.perform_update(serializer)
                obj = serializer.instance
                if kind == 'shopping_list' and (op == 'create' or access_data):
                    from .shopping_access import set_shopping_access
                    set_shopping_access(obj, actor=request.user, allow_initialize=op == 'create',
                                        **{'visibility': access_data.get('visibility', 'family' if op == 'create' else None),
                                           'visible_member_ids': access_data.get('visible_members'),
                                           'responsible_member_ids': access_data.get('responsible_members'),
                                           'audience_group': access_data.get('audience_group')})
            elif op == 'delete':
                view.perform_destroy(obj)
                obj.version += 1
            else:
                command = mutation.get('command')
                args = mutation.get('args') or {}
                if kind == 'shopping_list' and command == 'apply_template':
                    from .shopping_models import ShoppingTemplate
                    from .shopping_template_views import _apply_template
                    template = ShoppingTemplate.objects.filter(pk=args.get('template_id'), family=family, archived=False).first()
                    if not template:
                        raise ValidationError({'template_id': 'Template is unavailable.'})
                    _apply_template(template, obj, request.user)
                elif kind != 'task':
                    raise ValidationError({'command': 'Unsupported domain command.'})
                if not isinstance(args, dict):
                    raise ValidationError({'args': 'Expected an object.'})
                if kind == 'shopping_list':
                    pass
                elif command in {'complete_task', 'reopen_task'}:
                    from .unified_action_service import execute
                    execute(request.user, f'task:{obj.pk}', {**args, 'operation': 'complete' if command == 'complete_task' else 'reopen', 'request_id': str(mutation_id), 'source': 'ui'})
                elif command == 'move_task':
                    from .models import TaskWorkflowColumn
                    from .task_workflow import move_task
                    column = TaskWorkflowColumn.objects.filter(pk=args.get('column_id'), task_list__family=family).first()
                    if not column:
                        raise ValidationError({'column_id': 'Invalid workflow column.'})
                    move_task(obj, column, args.get('before_task_id'))
                else:
                    raise ValidationError({'command': 'Unsupported domain command.'})
                obj.refresh_from_db()
            result.update(status='applied', version=obj.version)
            if op != 'delete':
                obj.refresh_from_db()
                result['version'] = obj.version
                result['data'] = serialize(view, obj, kind)
            ProcessedMutation.objects.create(family=family, actor=request.user, mutation_id=mutation_id, fingerprint=fingerprint, result={k: v for k, v in result.items() if k != 'data'})
            return result
    except (APIException, DjangoValidationError, ValueError, TypeError, IntegrityError) as exc:
        status = exc.status_code if isinstance(exc, APIException) else 400
        code = {400: 'validation_error', 401: 'authentication_required', 403: 'permission_denied',
                404: 'not_found', 429: 'rate_limited'}.get(status, 'mutation_rejected')
        return {**result, 'status': 'rejected', 'code': code, 'http_status': status,
                'errors': json.loads(JSONRenderer().render(exc.detail)) if isinstance(exc, APIException) else {'detail': 'Invalid mutation.'}}


def synchronize(request, family, cursor, mutations, calendar_projection_key=None):
    results = [apply_mutation(request, family, mutation) for mutation in mutations]
    with sync_lock():
        clock = SyncSequence.objects.get(pk=1)
        reset = cursor is None or cursor < clock.retained_after or cursor > clock.cursor
        views = {kind: view_for(kind, request, family) for kind in SNAPSHOT_KEYS}
        visible = {kind: visible_queryset(view, kind, family) for kind, view in views.items()}
        # Every response includes an authoritative visibility manifest: revocation
        # removes stale local copies even when no domain row changed. No hidden IDs.
        manifest = {kind: [str(pk) for pk in queryset.values_list('pk', flat=True)] for kind, queryset in visible.items()}
        response = {'protocol_version': 1, 'mode': 'snapshot' if reset else 'delta',
                    'mutation_results': results, 'cursor': clock.cursor, 'visibility': manifest}
        if reset:
            snapshot = {}
            for kind, queryset in visible.items():
                if kind == 'event':
                    from .sync_calendar import in_window
                    queryset = in_window(queryset, family)
                snapshot[SNAPSHOT_KEYS[kind]] = [serialize(views[kind], obj, kind) for obj in queryset]
            response.update(reset_required=True, snapshot_cursor=clock.cursor, snapshot=snapshot)
        else:
            changes = []
            # Coalesce by entity. Data is serialized at the same locked watermark,
            # never combine an old cursor with a later unbounded object read.
            journal = SyncJournal.objects.filter(family=family, cursor__gt=cursor, cursor__lte=clock.cursor).order_by('cursor')
            latest = {}
            for entry in journal:
                latest[(entry.entity_type, entry.entity_id)] = entry
            for (kind, pk), entry in latest.items():
                if kind not in views:
                    continue
                obj = visible[kind].filter(pk=pk).first()
                if obj:
                    changes.append({'cursor': entry.cursor, 'entity_type': kind, 'entity_id': str(pk),
                                    'operation': 'update', 'version': obj.version,
                                    'changed_fields': entry.changed_fields, 'data': serialize(views[kind], obj, kind)})
                # Deletions/revocations are represented by the manifest, avoiding
                # disclosure of tombstone IDs for private/surprise entities.
            response['changes'] = changes
        from .action_projection import project_actions
        from .sync_calendar import projection
        from .calendar_recurrence import family_zone
        key = f'{timezone.now().astimezone(family_zone(family)).date().isoformat()}:{family.timezone}'
        events_changed = reset or SyncJournal.objects.filter(family=family, entity_type='event', cursor__gt=cursor or 0).exists()
        response['projections'] = {'actions': project_actions(user=request.user, family=family, scope='all', kind='all'),
                                  **projection(visible['event'], views['event'], family, request.user, serialize,
                                               events_changed or calendar_projection_key != key)}
        return response
