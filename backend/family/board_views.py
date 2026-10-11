import uuid

from django.db import transaction
from django.db.models import Min
from django.http import FileResponse, Http404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .board_reorder import plan_board_positions
from .models import BoardPost, BoardImage, Membership
from .domain_notifications import notify_domain_event
from .pin_adapters import (
    ADAPTER_KEYS,
    canonical_adapter_key,
    legacy_kind_for_adapter_key,
    resolve_pin_target,
    resolve_pin_targets,
    validate_pin_target,
)
from .pin_visibility import (
    effective_scope_for_user,
    pin_scope_queryset,
    source_object_visible,
    source_scope_for_target,
)
from .private_images import optimize_image, store_image, remove_image, image_path


class BoardPagination(PageNumberPagination):
    page_size = 20


class SelectedMembershipIdsField(serializers.ListField):
    child = serializers.UUIDField()

    def get_attribute(self, instance):
        return instance

    def to_representation(self, obj):
        request = self.parent.context.get('request')
        if not request or obj.author_id != request.user.id:
            return []
        return [str(membership.id) for membership in obj.visible_to_memberships.all()]


class BoardSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_reorder = serializers.SerializerMethodField()
    can_change_pin_visibility = serializers.SerializerMethodField()
    can_share_source = serializers.SerializerMethodField()
    can_interact = serializers.SerializerMethodField()
    effective_scope = serializers.SerializerMethodField()
    selected_membership_ids = SelectedMembershipIdsField(required=False)
    target = serializers.SerializerMethodField()

    class Meta:
        model = BoardPost
        fields = [
            'id', 'family', 'author', 'author_name', 'text', 'kind', 'adapter_key',
            'target_id', 'target', 'visibility', 'selected_membership_ids',
            'effective_scope', 'can_change_pin_visibility', 'can_share_source',
            'can_interact', 'position', 'created_at', 'updated_at', 'images',
            'can_edit', 'can_delete', 'can_reorder',
        ]
        read_only_fields = ['author', 'position', 'created_at', 'updated_at']

    def _target_for(self, obj):
        resolved = self.context.get('pin_targets')
        if resolved is not None and obj.id in resolved:
            return resolved[obj.id]
        cache = self.context.setdefault('_pin_target_cache', {})
        if obj.id not in cache:
            cache[obj.id] = resolve_pin_target(obj, self.context['request'].user)
        return cache[obj.id]

    def _source_unavailable(self, obj):
        if not obj.target_id:
            return False
        target = self._target_for(obj)
        return isinstance(target, dict) and target.get('available') is False

    def _effective_scope_for(self, obj):
        cache = self.context.setdefault('_pin_effective_scope_cache', {})
        if obj.id not in cache:
            if self._source_unavailable(obj):
                cache[obj.id] = 'none'
            else:
                cache[obj.id] = effective_scope_for_user(self.context['request'].user, obj)
        return cache[obj.id]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self._source_unavailable(instance):
            # #219 keeps a neutral unavailable lifecycle shell, but #220 must not
            # leak pin captions, uploaded media or author/activity metadata once
            # the canonical source ACL denies the viewer. Keep only lifecycle and
            # pin-management information needed to render/remove the stale shell.
            data['author'] = None
            data['author_name'] = ''
            data['text'] = ''
            data['images'] = []
            data['selected_membership_ids'] = []
            data['created_at'] = None
            data['updated_at'] = None
            data['can_edit'] = False
            data['can_reorder'] = False
            data['can_change_pin_visibility'] = False
            data['can_share_source'] = False
            data['can_interact'] = False
            data['effective_scope'] = 'none'
        return data

    def get_images(self, obj):
        if self._source_unavailable(obj):
            return []
        return [{'id': str(row.id), 'url': f'/api/board-images/{row.id}/', 'width': row.width, 'height': row.height} for row in obj.images.all()]

    def get_author_name(self, obj):
        if self._source_unavailable(obj):
            return ''
        names = self.context.get('author_names', {})
        return names.get((obj.family_id, obj.author_id)) or (obj.author.get_short_name() or obj.author.username if obj.author else '–')

    def get_can_edit(self, obj):
        if self._source_unavailable(obj):
            return False
        return obj.author_id == self.context['request'].user.id

    def get_can_delete(self, obj):
        return obj.author_id == self.context['request'].user.id or obj.family_id in self.context.get('moderated_families', set())

    def get_can_reorder(self, obj):
        if self._source_unavailable(obj):
            return False
        return obj.family_id in self.context.get('reorder_families', set())

    def get_can_change_pin_visibility(self, obj):
        return self.get_can_edit(obj)

    def get_can_share_source(self, obj):
        if self._source_unavailable(obj):
            return False
        target = self._target_for(obj)
        return bool(isinstance(target, dict) and target.get('can_share_source'))

    def get_target(self, obj):
        return self._target_for(obj)

    def get_effective_scope(self, obj):
        return self._effective_scope_for(obj)

    def get_can_interact(self, obj):
        return self._effective_scope_for(obj) != 'none'

    def validate(self, attrs):
        family = attrs.get('family') or getattr(self.instance, 'family', None)
        kind = attrs.get('kind', getattr(self.instance, 'kind', BoardPost.Kind.NOTE))
        target_id = attrs.get('target_id', getattr(self.instance, 'target_id', None))
        adapter_key = str(attrs.get('adapter_key', getattr(self.instance, 'adapter_key', '')) or '').strip()
        visibility = attrs.get('visibility', getattr(self.instance, 'visibility', BoardPost.Visibility.FAMILY))
        selected_ids = attrs.get('selected_membership_ids', serializers.empty)
        kind_supplied = 'kind' in getattr(self, 'initial_data', {})
        adapter_supplied = 'adapter_key' in getattr(self, 'initial_data', {})
        visibility_supplied = 'visibility' in getattr(self, 'initial_data', {})

        if adapter_key:
            if adapter_key not in ADAPTER_KEYS:
                raise serializers.ValidationError({'adapter_key': 'Unbekannter Pin-Adapter.'})
            expected_kind = legacy_kind_for_adapter_key(adapter_key)
            if (kind_supplied and kind != expected_kind) or (self.instance is not None and self.instance.kind != expected_kind):
                raise serializers.ValidationError({'adapter_key': 'Adapter und Pin-Typ widersprechen sich.'})
            kind = expected_kind
            attrs['kind'] = expected_kind
            attrs['adapter_key'] = adapter_key
        else:
            derived_key = canonical_adapter_key(legacy_kind=kind)
            if derived_key:
                adapter_key = derived_key
                attrs['adapter_key'] = derived_key
            elif adapter_supplied and attrs.get('adapter_key') not in ('', None):
                raise serializers.ValidationError({'adapter_key': 'Unbekannter Pin-Adapter.'})

        if family:
            user = self.context['request'].user
            membership = Membership.objects.filter(family=family, user=user).first()
            if not membership:
                # Fail before resolving a target or membership ids so a foreign
                # family cannot become an existence oracle.
                raise PermissionDenied('Kein Zugriff auf diese Familie.')
            if self.instance is None and membership.role == 'guest':
                raise PermissionDenied('Diese Rolle darf keine Pins erstellen.')
            validate_pin_target(kind, target_id, family.id, user, adapter_key=adapter_key)

            if self.instance is None and adapter_key and target_id and not visibility_supplied:
                source_visibility, source_memberships = source_scope_for_target(
                    user=user,
                    family_id=family.id,
                    adapter_key=adapter_key,
                    target_id=target_id,
                )
                attrs['visibility'] = source_visibility
                visibility = source_visibility
                if source_visibility == BoardPost.Visibility.SELECTED:
                    selected_ids = [row.id for row in source_memberships]
                    attrs['selected_membership_ids'] = source_memberships

            if selected_ids is not serializers.empty:
                requested = {str(value) for value in selected_ids}
                selected_memberships = list(Membership.objects.filter(family=family, id__in=selected_ids))
                if {str(row.id) for row in selected_memberships} != requested:
                    raise serializers.ValidationError({'selected_membership_ids': 'Ausgewählte Personen sind nicht verfügbar.'})
                attrs['selected_membership_ids'] = selected_memberships

            if visibility == BoardPost.Visibility.SELECTED:
                if selected_ids is serializers.empty:
                    has_existing = bool(
                        self.instance
                        and self.instance.visibility == BoardPost.Visibility.SELECTED
                        and self.instance.visible_to_memberships.exists()
                    )
                    if not has_existing:
                        raise serializers.ValidationError({'selected_membership_ids': 'Bitte mindestens eine Person auswählen.'})
                elif not attrs['selected_membership_ids']:
                    raise serializers.ValidationError({'selected_membership_ids': 'Bitte mindestens eine Person auswählen.'})
            elif selected_ids is not serializers.empty and attrs['selected_membership_ids']:
                raise serializers.ValidationError({'selected_membership_ids': 'Personen können nur bei „Ausgewählte Personen“ gesetzt werden.'})
        return attrs

    def create(self, validated_data):
        selected = validated_data.pop('selected_membership_ids', serializers.empty)
        instance = super().create(validated_data)
        if selected is not serializers.empty:
            instance.visible_to_memberships.set(selected)
        return instance

    def update(self, instance, validated_data):
        selected = validated_data.pop('selected_membership_ids', serializers.empty)
        instance = super().update(instance, validated_data)
        if instance.visibility != BoardPost.Visibility.SELECTED:
            instance.visible_to_memberships.clear()
        elif selected is not serializers.empty:
            instance.visible_to_memberships.set(selected)
        return instance


class BoardViewSet(viewsets.ModelViewSet):
    serializer_class = BoardSerializer
    pagination_class = BoardPagination
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        rows = BoardPost.objects.select_related('author', 'family').prefetch_related('images', 'visible_to_memberships')
        rows = pin_scope_queryset(self.request.user, rows)
        if self.request.query_params.get('family'):
            rows = rows.filter(family_id=self.request.query_params['family'])
        return rows

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['author_names'] = {(family, user): name for family, user, name in Membership.objects.filter(family__memberships__user=self.request.user).values_list('family_id', 'user_id', 'display_name')}
        context['moderated_families'] = set(Membership.objects.filter(user=self.request.user, role__in=['owner', 'adult']).values_list('family_id', flat=True))
        context['reorder_families'] = set(Membership.objects.filter(user=self.request.user).exclude(role='guest').values_list('family_id', flat=True))
        return context

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        context = self.get_serializer_context()
        context['pin_targets'] = resolve_pin_targets(rows, request.user)
        serializer = self.get_serializer(rows, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_create(self, serializer):
        family = serializer.validated_data['family']
        if not Membership.objects.filter(family=family, user=self.request.user).exclude(role='guest').exists():
            raise PermissionDenied('Diese Rolle darf keine Pins erstellen.')
        uploads = self.request.FILES.getlist('images')
        if len(uploads) > 4:
            raise ValidationError({'images': 'Maximal vier Bilder pro Pin.'})
        kind = serializer.validated_data.get('kind', BoardPost.Kind.NOTE)
        if uploads and kind not in (BoardPost.Kind.NOTE, BoardPost.Kind.PHOTO):
            raise ValidationError({'images': 'Bilder können nur an native Pinnwand-Inhalte angehängt werden.'})
        if uploads and kind == BoardPost.Kind.NOTE:
            kind = BoardPost.Kind.PHOTO
        if kind == BoardPost.Kind.PHOTO and not uploads:
            raise ValidationError({'images': 'Bitte mindestens ein Bild auswählen.'})
        if kind in (BoardPost.Kind.NOTE, BoardPost.Kind.PHOTO) and not serializer.validated_data.get('text', '').strip() and not uploads:
            raise ValidationError({'text': 'Bitte Text oder Bilder hinzufügen.'})
        optimized = [optimize_image(upload) for upload in uploads]
        keys = []
        try:
            with transaction.atomic():
                floor = BoardPost.objects.filter(family=family).aggregate(value=Min('position'))['value']
                post = serializer.save(author=self.request.user, kind=kind, position=(floor - 1000 if floor is not None else 0))
                for data, width, height in optimized:
                    key = store_image(data)
                    keys.append(key)
                    BoardImage.objects.create(post=post, key=key, width=width, height=height)
                transaction.on_commit(lambda: notify_domain_event(family, 'board.created', actor=self.request.user, context={'post_id': post.id}, url=f'/?page=board&post={post.id}&family={family.id}'))
        except Exception:
            for key in keys:
                remove_image(key)
            raise

    @transaction.atomic
    def perform_update(self, serializer):
        post = BoardPost.objects.select_for_update().get(pk=serializer.instance.pk)
        serializer.instance = post
        if post.author_id != self.request.user.id:
            raise PermissionDenied('Nur der Autor darf den Pin ändern.')
        if 'family' in serializer.validated_data and serializer.validated_data['family'].id != post.family_id:
            raise ValidationError({'family': 'Familie kann nicht geändert werden.'})
        if 'kind' in serializer.validated_data and serializer.validated_data['kind'] != post.kind:
            raise ValidationError({'kind': 'Der Pin-Typ kann nicht geändert werden.'})
        if 'adapter_key' in serializer.validated_data:
            expected_key = canonical_adapter_key(adapter_key=post.adapter_key, legacy_kind=post.kind) or canonical_adapter_key(legacy_kind=post.kind)
            if serializer.validated_data['adapter_key'] != expected_key:
                raise ValidationError({'adapter_key': 'Der Pin-Adapter kann nicht geändert werden.'})
        if 'target_id' in serializer.validated_data and serializer.validated_data['target_id'] != post.target_id:
            raise ValidationError({'target_id': 'Das verknüpfte Objekt kann nicht geändert werden.'})
        if self.request.FILES:
            raise ValidationError({'images': 'Bilder können nach Veröffentlichung nur entfernt werden.'})
        if post.kind in (BoardPost.Kind.NOTE, BoardPost.Kind.PHOTO) and not serializer.validated_data.get('text', post.text).strip() and not post.images.exists():
            raise ValidationError({'text': 'Ein Pin darf nicht leer sein.'})
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        instance = BoardPost.objects.select_for_update().get(pk=instance.pk)
        if instance.author_id != self.request.user.id and not Membership.objects.filter(family=instance.family, user=self.request.user, role__in=['owner', 'adult']).exists():
            raise PermissionDenied('Nur Autor oder Erwachsene dürfen Pins löschen.')
        instance.delete()

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        family_id = request.data.get('family')
        membership = Membership.objects.filter(family_id=family_id, user=request.user).exclude(role='guest').first()
        if not membership:
            raise PermissionDenied('Diese Rolle darf die Pinnwand nicht anordnen.')
        ids = request.data.get('ids')
        if not isinstance(ids, list) or not ids or len(ids) > 500 or len({str(value) for value in ids}) != len(ids):
            raise ValidationError({'ids': 'Ungültige Reihenfolge.'})
        try:
            wanted = [uuid.UUID(str(value)) for value in ids]
        except (TypeError, ValueError, AttributeError):
            raise ValidationError({'ids': 'Ungültige Pin-ID.'})

        allowed_ids = set(
            pin_scope_queryset(
                request.user,
                BoardPost.objects.filter(family_id=family_id),
            ).values_list('id', flat=True)
        )
        if any(value not in allowed_ids for value in wanted):
            # The same response is used for random, foreign and hidden pin ids.
            raise ValidationError({'ids': 'Pins sind für diese Pinnwand nicht verfügbar.'})

        with transaction.atomic():
            current = list(BoardPost.objects.select_for_update().filter(family_id=family_id).order_by('position', '-created_at', '-id'))
            visible_current = [row for row in current if row.id in allowed_ids]
            by_id = {row.id: row for row in visible_current}
            wanted_set = set(wanted)
            visible_ordered = [by_id[value] for value in wanted] + [row for row in visible_current if row.id not in wanted_set]
            visible_iter = iter(visible_ordered)
            ordered = [next(visible_iter) if row.id in allowed_ids else row for row in current]
            planned = plan_board_positions(current, ordered)
            changed = []
            for row, position in planned:
                row.position = position
                changed.append(row)
            if changed:
                BoardPost.objects.bulk_update(changed, ['position'])
        return Response({'ids': [str(row.id) for row in visible_ordered]})


@api_view(['GET', 'DELETE'])
@transaction.atomic
def board_image(request, image_id):
    visible_posts = pin_scope_queryset(request.user, BoardPost.objects.all()).values_list('id', flat=True)
    row = BoardImage.objects.select_related('post', 'post__family').filter(id=image_id, post_id__in=visible_posts).first()
    if not row or (row.post.target_id and not source_object_visible(request.user, row.post)):
        raise Http404()
    if request.method == 'DELETE':
        row.post = BoardPost.objects.select_for_update().get(pk=row.post_id)
        if row.post.author_id != request.user.id and not Membership.objects.filter(family=row.post.family, user=request.user, role__in=['owner', 'adult']).exists():
            raise PermissionDenied()
        if not row.post.text.strip() and row.post.images.count() == 1:
            raise ValidationError({'detail': 'Der Pin darf nicht leer sein.'})
        row.delete()
        return Response(status=204)
    path = image_path(row.key)
    if not path.exists():
        raise Http404()
    try:
        response = FileResponse(path.open('rb'), content_type='image/webp')
    except FileNotFoundError:
        raise Http404()
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response