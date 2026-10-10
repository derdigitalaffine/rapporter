import uuid

from django.db import transaction
from django.db.models import Min, Q
from django.http import FileResponse, Http404
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import BoardPost, BoardImage, FamilyEvent, Membership, Note, ShoppingItem, Task
from .domain_notifications import notify_domain_event
from .private_images import optimize_image, store_image, remove_image, image_path


REFERENCE_KINDS = {BoardPost.Kind.EVENT, BoardPost.Kind.TASK, BoardPost.Kind.NOTE_REF, BoardPost.Kind.SHOPPING}


class BoardPagination(PageNumberPagination):
    page_size = 20


def _note_visible(note_id, family_id, user):
    return Note.objects.filter(id=note_id, family_id=family_id).filter(Q(author=user) | Q(shares__user=user)).distinct().first()


def _target(post, user):
    """Resolve a pin target for this viewer. A pin never grants access to its target."""
    if not post.target_id:
        return None
    if post.kind == BoardPost.Kind.EVENT:
        row = FamilyEvent.objects.filter(id=post.target_id, family_id=post.family_id).first()
        if row:
            return {'id': str(row.id), 'kind': 'event', 'title': row.title, 'subtitle': row.starts_at, 'event_type': row.type, 'url': f'/?page=calendar&event={row.id}'}
    elif post.kind == BoardPost.Kind.TASK:
        row = Task.objects.filter(id=post.target_id, family_id=post.family_id).exclude(hidden_from_user=user).first()
        if row:
            return {'id': str(row.id), 'kind': 'task', 'title': row.title, 'subtitle': row.due_at, 'completed': bool(row.completed_at), 'url': f'/?page=tasks&task={row.id}'}
    elif post.kind == BoardPost.Kind.NOTE_REF:
        row = _note_visible(post.target_id, post.family_id, user)
        if row:
            preview = (row.body or '').strip().replace('\n', ' ')[:180]
            return {'id': str(row.id), 'kind': 'note_ref', 'title': row.title or 'Notiz', 'subtitle': preview, 'url': f'/?page=notes&note={row.id}'}
    elif post.kind == BoardPost.Kind.SHOPPING:
        row = ShoppingItem.objects.filter(id=post.target_id, shopping_list__family_id=post.family_id).select_related('shopping_list').first()
        if row:
            return {'id': str(row.id), 'kind': 'shopping', 'title': row.name, 'subtitle': row.shopping_list.name, 'checked': row.checked, 'url': '/?page=shopping'}
    return {'id': str(post.target_id), 'kind': post.kind, 'available': False}


def _validate_target(kind, target_id, family_id, user):
    if kind not in REFERENCE_KINDS:
        if target_id:
            raise ValidationError({'target_id': 'Dieser Pinnwand-Typ darf kein Ziel besitzen.'})
        return
    if not target_id:
        raise ValidationError({'target_id': 'Bitte ein Objekt zum Anpinnen auswählen.'})
    try:
        target_id = uuid.UUID(str(target_id))
    except (TypeError, ValueError, AttributeError):
        raise ValidationError({'target_id': 'Ungültiges Ziel.'})
    if kind == BoardPost.Kind.EVENT:
        visible = FamilyEvent.objects.filter(id=target_id, family_id=family_id).exists()
    elif kind == BoardPost.Kind.TASK:
        visible = Task.objects.filter(id=target_id, family_id=family_id).exclude(hidden_from_user=user).exists()
    elif kind == BoardPost.Kind.NOTE_REF:
        visible = bool(_note_visible(target_id, family_id, user))
    else:
        visible = ShoppingItem.objects.filter(id=target_id, shopping_list__family_id=family_id).exists()
    if not visible:
        raise ValidationError({'target_id': 'Das ausgewählte Objekt ist in dieser Familie nicht verfügbar.'})


class BoardSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_reorder = serializers.SerializerMethodField()
    target = serializers.SerializerMethodField()

    class Meta:
        model = BoardPost
        fields = ['id', 'family', 'author', 'author_name', 'text', 'kind', 'target_id', 'target', 'position', 'created_at', 'updated_at', 'images', 'can_edit', 'can_delete', 'can_reorder']
        read_only_fields = ['author', 'position', 'created_at', 'updated_at']

    def get_images(self, obj):
        return [{'id': str(row.id), 'url': f'/api/board-images/{row.id}/', 'width': row.width, 'height': row.height} for row in obj.images.all()]

    def get_author_name(self, obj):
        names = self.context.get('author_names', {})
        return names.get((obj.family_id, obj.author_id)) or (obj.author.get_short_name() or obj.author.username if obj.author else '–')

    def get_can_edit(self, obj):
        return obj.author_id == self.context['request'].user.id

    def get_can_delete(self, obj):
        return self.get_can_edit(obj) or obj.family_id in self.context.get('moderated_families', set())

    def get_can_reorder(self, obj):
        return obj.family_id in self.context.get('reorder_families', set())

    def get_target(self, obj):
        return _target(obj, self.context['request'].user)

    def validate(self, attrs):
        family = attrs.get('family') or getattr(self.instance, 'family', None)
        kind = attrs.get('kind', getattr(self.instance, 'kind', BoardPost.Kind.NOTE))
        target_id = attrs.get('target_id', getattr(self.instance, 'target_id', None))
        if family:
            _validate_target(kind, target_id, family.id, self.context['request'].user)
        return attrs


class BoardViewSet(viewsets.ModelViewSet):
    serializer_class = BoardSerializer
    pagination_class = BoardPagination
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        rows = BoardPost.objects.filter(family__status='active', family__memberships__user=self.request.user).select_related('author', 'family').prefetch_related('images')
        if self.request.query_params.get('family'):
            rows = rows.filter(family_id=self.request.query_params['family'])
        return rows

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['author_names'] = {(family, user): name for family, user, name in Membership.objects.filter(family__memberships__user=self.request.user).values_list('family_id', 'user_id', 'display_name')}
        context['moderated_families'] = set(Membership.objects.filter(user=self.request.user, role__in=['owner', 'adult']).values_list('family_id', flat=True))
        context['reorder_families'] = set(Membership.objects.filter(user=self.request.user).exclude(role='guest').values_list('family_id', flat=True))
        return context

    def perform_create(self, serializer):
        family = serializer.validated_data['family']
        if not Membership.objects.filter(family=family, user=self.request.user).exclude(role='guest').exists():
            raise PermissionDenied('Diese Rolle darf keine Pins erstellen.')
        uploads = self.request.FILES.getlist('images')
        if len(uploads) > 4:
            raise ValidationError({'images': 'Maximal vier Bilder pro Pin.'})
        kind = serializer.validated_data.get('kind', BoardPost.Kind.NOTE)
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
        with transaction.atomic():
            current = list(BoardPost.objects.select_for_update().filter(family_id=family_id).order_by('position', '-created_at', '-id'))
            by_id = {row.id: row for row in current}
            if any(value not in by_id for value in wanted):
                raise ValidationError({'ids': 'Pins gehören nicht zu dieser Familie.'})
            ordered = [by_id[value] for value in wanted] + [row for row in current if row.id not in set(wanted)]
            for index, row in enumerate(ordered):
                row.position = index * 1000
            BoardPost.objects.bulk_update(ordered, ['position'])
        return Response({'ids': [str(row.id) for row in ordered]})


@api_view(['GET', 'DELETE'])
@transaction.atomic
def board_image(request, image_id):
    row = BoardImage.objects.filter(id=image_id, post__family__memberships__user=request.user, post__family__status='active').first()
    if not row:
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
