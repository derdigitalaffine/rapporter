from django.db import transaction
from django.http import FileResponse, Http404
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from .models import BoardPost, BoardImage, Membership
from .domain_notifications import notify_domain_event
from .private_images import optimize_image, store_image, remove_image, image_path

class BoardPagination(PageNumberPagination):
    page_size = 20

class BoardSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    class Meta:
        model = BoardPost
        fields = ['id', 'family', 'author', 'author_name', 'text', 'created_at', 'updated_at', 'images', 'can_edit', 'can_delete']
        read_only_fields = ['author', 'created_at', 'updated_at']
    def get_images(self, obj):
        return [{'id': str(row.id), 'url': f'/api/board-images/{row.id}/', 'width': row.width, 'height': row.height} for row in obj.images.all()]
    def get_author_name(self, obj):
        names = self.context.get('author_names', {})
        return names.get((obj.family_id, obj.author_id)) or (obj.author.get_short_name() or obj.author.username if obj.author else '–')
    def get_can_edit(self, obj):
        return obj.author_id == self.context['request'].user.id
    def get_can_delete(self, obj):
        return self.get_can_edit(obj) or obj.family_id in self.context.get('moderated_families', set())

class BoardViewSet(viewsets.ModelViewSet):
    serializer_class = BoardSerializer
    pagination_class = BoardPagination
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    def get_queryset(self):
        rows = BoardPost.objects.filter(family__memberships__user=self.request.user).select_related('author', 'family').prefetch_related('images')
        if self.request.query_params.get('family'):
            rows = rows.filter(family_id=self.request.query_params['family'])
        return rows
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['author_names'] = {(family, user): name for family, user, name in Membership.objects.filter(family__memberships__user=self.request.user).values_list('family_id', 'user_id', 'display_name')}
        context['moderated_families'] = set(Membership.objects.filter(user=self.request.user, role__in=['owner', 'adult']).values_list('family_id', flat=True))
        return context
    def perform_create(self, serializer):
        family = serializer.validated_data['family']
        if not Membership.objects.filter(family=family, user=self.request.user).exclude(role='guest').exists():
            raise PermissionDenied('Diese Rolle darf keine Beiträge erstellen.')
        uploads = self.request.FILES.getlist('images')
        if len(uploads) > 4:
            raise ValidationError({'images': 'Maximal vier Bilder pro Beitrag.'})
        if not serializer.validated_data.get('text', '').strip() and not uploads:
            raise ValidationError({'text': 'Bitte Text oder Bilder hinzufügen.'})
        optimized = [optimize_image(upload) for upload in uploads]
        keys = []
        try:
            with transaction.atomic():
                post = serializer.save(author=self.request.user)
                for data, width, height in optimized:
                    key = store_image(data); keys.append(key)
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
            raise PermissionDenied('Nur der Autor darf den Text ändern.')
        if 'family' in serializer.validated_data and serializer.validated_data['family'].id != post.family_id:
            raise ValidationError({'family': 'Familie kann nicht geändert werden.'})
        if self.request.FILES:
            raise ValidationError({'images': 'Bilder können nach Veröffentlichung nur entfernt werden.'})
        if not serializer.validated_data.get('text', post.text).strip() and not post.images.exists():
            raise ValidationError({'text': 'Ein Beitrag darf nicht leer sein.'})
        serializer.save()
    @transaction.atomic
    def perform_destroy(self, instance):
        instance = BoardPost.objects.select_for_update().get(pk=instance.pk)
        if instance.author_id != self.request.user.id and not Membership.objects.filter(family=instance.family, user=self.request.user, role__in=['owner', 'adult']).exists():
            raise PermissionDenied('Nur Autor oder Erwachsene dürfen Beiträge löschen.')
        instance.delete()

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
            raise ValidationError({'detail': 'Der Beitrag darf nicht leer sein.'})
        row.delete()
        from rest_framework.response import Response
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
