import math
import re
import uuid
from copy import deepcopy

from django.db import transaction
from django.db.models import Q
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .context_links import (
    ContextLinkPermissionDenied,
    create_context_link,
    default_context_registry,
    list_context_links,
)
from .models import Family, Membership, Note, NoteRevision, NoteShare, Task, TaskList


CHECKLIST_ITEM_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
MAX_BLOCKS = 100
MAX_CHECKLIST_ITEMS = 500
MAX_BLOCK_TEXT = 50000


def validate_drawing(value):
    if not isinstance(value, list) or len(value) > 250:
        raise ValidationError('drawing_limit')
    total = 0
    for stroke in value:
        if not isinstance(stroke, dict) or set(stroke) != {'color', 'width', 'points'}:
            raise ValidationError('invalid_drawing')
        if not isinstance(stroke['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', stroke['color']):
            raise ValidationError('invalid_color')
        width = stroke['width']
        if isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isfinite(width) or not 1 <= width <= 30:
            raise ValidationError('invalid_width')
        points = stroke['points']
        if not isinstance(points, list) or not 1 <= len(points) <= 2000:
            raise ValidationError('invalid_points')
        total += len(points)
        if total > 20000:
            raise ValidationError('drawing_limit')
        for point in points:
            if not isinstance(point, list) or len(point) != 2 or any(
                isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not 0 <= n <= 1000
                for n in point
            ):
                raise ValidationError('invalid_point')
    return value


def _text(value, *, max_length, code, allow_blank=True):
    if not isinstance(value, str) or len(value) > max_length or (not allow_blank and not value.strip()):
        raise ValidationError(code)
    return value


def validate_note_blocks(value):
    if not isinstance(value, list) or len(value) > MAX_BLOCKS:
        raise ValidationError('invalid_blocks')
    cleaned = []
    total_text = 0
    total_items = 0
    seen_item_ids = set()
    date_field = serializers.DateTimeField(allow_null=True, required=False)

    for block in value:
        if not isinstance(block, dict) or not isinstance(block.get('type'), str):
            raise ValidationError('invalid_block')
        block_type = block['type']
        if block_type == 'paragraph':
            if set(block) != {'type', 'text'}:
                raise ValidationError('invalid_paragraph')
            text = _text(block['text'], max_length=10000, code='invalid_paragraph')
            clean = {'type': 'paragraph', 'text': text}
            total_text += len(text)
        elif block_type == 'heading':
            if set(block) != {'type', 'text', 'level'} or block.get('level') not in (2, 3):
                raise ValidationError('invalid_heading')
            text = _text(block['text'], max_length=500, code='invalid_heading', allow_blank=False)
            clean = {'type': 'heading', 'text': text, 'level': block['level']}
            total_text += len(text)
        elif block_type == 'panel':
            if set(block) != {'type', 'tone', 'text'} or block.get('tone') not in ('info', 'warning'):
                raise ValidationError('invalid_panel')
            text = _text(block['text'], max_length=5000, code='invalid_panel')
            clean = {'type': 'panel', 'tone': block['tone'], 'text': text}
            total_text += len(text)
        elif block_type == 'checklist':
            if set(block) != {'type', 'items'} or not isinstance(block.get('items'), list):
                raise ValidationError('invalid_checklist')
            items = []
            for item in block['items']:
                total_items += 1
                if total_items > MAX_CHECKLIST_ITEMS or not isinstance(item, dict):
                    raise ValidationError('invalid_checklist')
                allowed = {'id', 'text', 'checked', 'due_at', 'assignee', 'task_id'}
                if set(item) - allowed or not {'id', 'text', 'checked'} <= set(item):
                    raise ValidationError('invalid_checklist_item')
                item_id = item.get('id')
                if not isinstance(item_id, str) or not CHECKLIST_ITEM_ID_RE.fullmatch(item_id) or item_id in seen_item_ids:
                    raise ValidationError('invalid_checklist_item_id')
                seen_item_ids.add(item_id)
                text = _text(item.get('text'), max_length=180, code='invalid_checklist_item', allow_blank=False)
                if type(item.get('checked')) is not bool:
                    raise ValidationError('invalid_checklist_item')
                clean_item = {'id': item_id, 'text': text, 'checked': item['checked']}
                total_text += len(text)
                if 'due_at' in item and item['due_at'] not in (None, ''):
                    try:
                        parsed = date_field.run_validation(item['due_at'])
                    except serializers.ValidationError:
                        raise ValidationError('invalid_checklist_due_at') from None
                    clean_item['due_at'] = parsed.isoformat()
                if 'assignee' in item and item['assignee'] is not None:
                    assignee = item['assignee']
                    if isinstance(assignee, bool) or not isinstance(assignee, int) or assignee <= 0:
                        raise ValidationError('invalid_checklist_assignee')
                    clean_item['assignee'] = assignee
                if 'task_id' in item and item['task_id']:
                    try:
                        clean_item['task_id'] = str(uuid.UUID(str(item['task_id'])))
                    except (TypeError, ValueError, AttributeError):
                        raise ValidationError('invalid_checklist_task') from None
                items.append(clean_item)
            clean = {'type': 'checklist', 'items': items}
        else:
            # No arbitrary HTML/embed block. New block types need an explicit contract.
            raise ValidationError('unsupported_block_type')
        cleaned.append(clean)

    if total_text > MAX_BLOCK_TEXT:
        raise ValidationError('blocks_text_limit')
    return cleaned


def _task_links(blocks):
    result = {}
    for block in blocks or []:
        if isinstance(block, dict) and block.get('type') == 'checklist':
            for item in block.get('items') or []:
                if isinstance(item, dict) and item.get('id') and item.get('task_id'):
                    result[item['id']] = str(item['task_id'])
    return result


class NoteSerializer(serializers.ModelSerializer):
    permission = serializers.SerializerMethodField()
    shares = serializers.SerializerMethodField()
    body = serializers.CharField(max_length=50000, allow_blank=True, required=False, trim_whitespace=False)
    drawing = serializers.JSONField(required=False, validators=[validate_drawing])
    blocks = serializers.JSONField(required=False)

    class Meta:
        model = Note
        fields = [
            'id', 'family', 'author', 'title', 'body', 'drawing', 'pinned', 'extended_mode', 'blocks',
            'version', 'created_at', 'updated_at', 'permission', 'shares',
        ]
        read_only_fields = ['author', 'version', 'created_at', 'updated_at']

    def get_permission(self, obj):
        user = self.context['request'].user
        return 'owner' if obj.author_id == user.id else next((s.permission for s in obj.shares.all() if s.user_id == user.id), 'read')

    def get_shares(self, obj):
        if obj.author_id != self.context['request'].user.id:
            return []
        return [{'user': s.user_id, 'permission': s.permission} for s in obj.shares.all()]

    def validate_family(self, family):
        if not Membership.objects.filter(family=family, user=self.context['request'].user).exists() or family.status != Family.Status.ACTIVE:
            raise ValidationError('invalid_family')
        if self.instance and self.instance.family_id != family.id:
            raise ValidationError('immutable_family')
        return family

    def validate_blocks(self, value):
        return validate_note_blocks(value)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        family = attrs.get('family') or (self.instance.family if self.instance else None)
        blocks = attrs.get('blocks', self.instance.blocks if self.instance else [])
        extended_mode = attrs.get('extended_mode', self.instance.extended_mode if self.instance else False)
        if blocks and not extended_mode:
            raise serializers.ValidationError({'blocks': 'extended_mode_required'})

        old_task_ids = _task_links(self.instance.blocks if self.instance else [])
        for block in blocks or []:
            if block.get('type') != 'checklist':
                continue
            for item in block['items']:
                old_task_id = old_task_ids.get(item['id'])
                supplied_task_id = item.get('task_id')
                if old_task_id:
                    if supplied_task_id and supplied_task_id != old_task_id:
                        raise serializers.ValidationError({'blocks': 'task_link_server_managed'})
                    item['task_id'] = old_task_id
                elif supplied_task_id:
                    raise serializers.ValidationError({'blocks': 'task_link_server_managed'})
                assignee = item.get('assignee')
                if assignee is not None and (not family or not Membership.objects.filter(family=family, user_id=assignee).exists()):
                    raise serializers.ValidationError({'blocks': 'invalid_checklist_assignee'})
        return attrs


class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        qs = (
            Note.objects.filter(family__status=Family.Status.ACTIVE, family__memberships__user=user)
            .filter(Q(author=user) | Q(shares__user=user))
            .distinct()
            .select_related('author')
            .prefetch_related('shares')
        )
        if self.request.query_params.get('family'):
            try:
                family_id = uuid.UUID(self.request.query_params['family'])
            except (ValueError, TypeError):
                raise ValidationError('invalid_family')
            qs = qs.filter(family_id=family_id)
        query = self.request.query_params.get('search', '')[:200]
        if query:
            qs = qs.filter(Q(title__icontains=query) | Q(body__icontains=query))
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            note = serializer.save(author=self.request.user)
            self.snapshot(note)

    def snapshot(self, note):
        NoteRevision.objects.create(
            note=note,
            actor=self.request.user,
            version=note.version,
            title=note.title,
            body=note.body,
            drawing=note.drawing,
            extended_mode=note.extended_mode,
            blocks=note.blocks,
        )
        stale = list(note.revisions.order_by('-version').values_list('id', flat=True)[20:])
        NoteRevision.objects.filter(id__in=stale).delete()

    def may_edit(self, note):
        if note.author_id != self.request.user.id and not note.shares.filter(user=self.request.user, permission='edit').exists():
            raise PermissionDenied('read_only')

    def partial_update(self, request, *args, **kwargs):
        visible = self.get_object()
        with transaction.atomic():
            note = Note.objects.select_for_update().get(pk=visible.pk)
            if note.author_id != request.user.id and not note.shares.filter(user=request.user).exists():
                raise PermissionDenied('access_revoked')
            self.may_edit(note)
            if isinstance(request.data.get('version'), bool) or not isinstance(request.data.get('version'), int) or request.data.get('version') != note.version:
                return Response({'detail': 'note_conflict', 'current': self.get_serializer(note).data}, status=409)
            serializer = self.get_serializer(note, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save(version=note.version + 1)
            self.snapshot(note)
            return Response(serializer.data)

    def perform_destroy(self, instance):
        if instance.author_id != self.request.user.id:
            raise PermissionDenied('owner_only')
        instance.delete()

    @action(detail=True, methods=['post'])
    def sharing(self, request, pk=None):
        visible = self.get_object()
        with transaction.atomic():
            note = Note.objects.select_for_update().get(pk=visible.pk)
            if note.author_id != request.user.id:
                raise PermissionDenied('owner_only')
            if isinstance(request.data.get('version'), bool) or not isinstance(request.data.get('version'), int) or request.data.get('version') != note.version:
                return Response({'detail': 'note_conflict'}, status=409)
            shares = request.data.get('shares')
            if not isinstance(shares, list) or len(shares) > 50:
                raise ValidationError('invalid_shares')
            cleaned = {}
            for share in shares:
                if not isinstance(share, dict) or share.get('permission') not in ['read', 'edit']:
                    raise ValidationError('invalid_permission')
                uid = share.get('user')
                if isinstance(uid, bool) or not isinstance(uid, int) or uid == note.author_id or not Membership.objects.filter(family=note.family, user_id=uid).exists():
                    raise ValidationError('invalid_member')
                cleaned[uid] = share['permission']
            note.shares.all().delete()
            NoteShare.objects.bulk_create([NoteShare(note=note, user_id=uid, permission=permission) for uid, permission in cleaned.items()])
            note.version += 1
            note.save(update_fields=['version', 'updated_at'])
            self.snapshot(note)
            return Response(self.get_serializer(note).data)

    @action(detail=True, methods=['post'], url_path='checklist-task')
    def checklist_task(self, request, pk=None):
        visible = self.get_object()
        item_id = request.data.get('item_id')
        if not isinstance(item_id, str) or not CHECKLIST_ITEM_ID_RE.fullmatch(item_id):
            raise ValidationError({'item_id': 'invalid_checklist_item_id'})

        with transaction.atomic():
            note = Note.objects.select_for_update().get(pk=visible.pk)
            if note.author_id != request.user.id and not note.shares.filter(user=request.user).exists():
                raise PermissionDenied('access_revoked')
            self.may_edit(note)
            if not note.extended_mode:
                raise ValidationError('extended_mode_required')

            blocks = deepcopy(note.blocks)
            target = None
            for block in blocks:
                if block.get('type') != 'checklist':
                    continue
                for item in block.get('items', []):
                    if item.get('id') == item_id:
                        target = item
                        break
                if target is not None:
                    break
            if target is None:
                raise ValidationError({'item_id': 'checklist_item_not_found'})

            existing_task = None
            if target.get('task_id'):
                try:
                    existing_task = Task.objects.filter(family=note.family, pk=target['task_id']).first()
                except (ValueError, TypeError):
                    existing_task = None
            if existing_task is not None:
                return Response({'created': False, 'task': self._task_payload(existing_task), 'note': self.get_serializer(note).data})

            assignee = None
            if target.get('assignee') is not None:
                membership = Membership.objects.filter(family=note.family, user_id=target['assignee']).select_related('user').first()
                if not membership:
                    raise ValidationError({'item_id': 'invalid_checklist_assignee'})
                assignee = membership.user
            due_at = None
            if target.get('due_at'):
                try:
                    due_at = serializers.DateTimeField().run_validation(target['due_at'])
                except serializers.ValidationError:
                    raise ValidationError({'item_id': 'invalid_checklist_due_at'}) from None

            task_list, _ = TaskList.objects.get_or_create(
                family=note.family,
                name='Allgemein',
                defaults={'icon': 'list-check'},
            )
            task = Task.objects.create(
                family=note.family,
                task_list=task_list,
                title=target['text'].strip(),
                due_at=due_at,
                assignee=assignee,
                created_by=request.user,
                source='note_checklist',
            )

            # A converted task inherits compatible visible note contexts via the
            # canonical registry; the link remains metadata and never expands ACLs.
            registry = default_context_registry()
            for row in list_context_links(
                user=request.user,
                family=note.family,
                anchor_type='note',
                anchor_id=note.id,
                limit=100,
                registry=registry,
            ):
                if row.link.source_type != 'note':
                    continue
                relation = registry.relation_adapter(row.link.relation_key)
                if not relation.allows('task', row.link.context_type):
                    continue
                try:
                    create_context_link(
                        user=request.user,
                        family=note.family,
                        source_type='task',
                        source_id=task.id,
                        context_type=row.link.context_type,
                        context_id=row.link.context_id,
                        relation_key=row.link.relation_key,
                        registry=registry,
                    )
                except ContextLinkPermissionDenied:
                    raise PermissionDenied('context_link_forbidden') from None

            target['task_id'] = str(task.id)
            note.blocks = blocks
            note.version += 1
            note.save(update_fields=['blocks', 'version', 'updated_at'])
            self.snapshot(note)
            return Response(
                {'created': True, 'task': self._task_payload(task), 'note': self.get_serializer(note).data},
                status=status.HTTP_201_CREATED,
            )

    @staticmethod
    def _task_payload(task):
        return {
            'id': str(task.id),
            'title': task.title,
            'due_at': task.due_at,
            'assignee': task.assignee_id,
            'source': task.source,
        }

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        note = self.get_object()
        if note.author_id != request.user.id:
            raise PermissionDenied('owner_only')
        rows = note.revisions.all()
        page = self.paginate_queryset(rows)
        data = [
            {
                'id': r.id,
                'version': r.version,
                'title': r.title,
                'body': r.body,
                'drawing': r.drawing,
                'extended_mode': r.extended_mode,
                'blocks': r.blocks,
                'created_at': r.created_at,
                'actor': r.actor_id,
            }
            for r in (page if page is not None else rows)
        ]
        return self.get_paginated_response(data) if page is not None else Response(data)
