import uuid
import math
import re
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Family, Membership, Note, NoteShare, NoteRevision


def validate_drawing(value):
    if not isinstance(value, list) or len(value) > 250:
        raise ValidationError('drawing_limit')
    total = 0
    for stroke in value:
        if not isinstance(stroke, dict) or set(stroke) != {'color','width','points'}:
            raise ValidationError('invalid_drawing')
        if not isinstance(stroke['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', stroke['color']):
            raise ValidationError('invalid_color')
        width = stroke['width']
        if isinstance(width, bool) or not isinstance(width, (int,float)) or not math.isfinite(width) or not 1 <= width <= 30:
            raise ValidationError('invalid_width')
        points = stroke['points']
        if not isinstance(points, list) or not 1 <= len(points) <= 2000:
            raise ValidationError('invalid_points')
        total += len(points)
        if total > 20000:
            raise ValidationError('drawing_limit')
        for point in points:
            if not isinstance(point, list) or len(point) != 2 or any(isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not 0 <= n <= 1000 for n in point):
                raise ValidationError('invalid_point')
    return value

class NoteSerializer(serializers.ModelSerializer):
    permission = serializers.SerializerMethodField()
    shares = serializers.SerializerMethodField()
    body = serializers.CharField(max_length=50000, allow_blank=True, required=False, trim_whitespace=False)
    drawing = serializers.JSONField(required=False, validators=[validate_drawing])
    class Meta:
        model = Note
        fields = ['id','family','author','title','body','drawing','pinned','version','created_at','updated_at','permission','shares']
        read_only_fields = ['author','version','created_at','updated_at']
    def get_permission(self, obj):
        user = self.context['request'].user
        return 'owner' if obj.author_id == user.id else next((s.permission for s in obj.shares.all() if s.user_id == user.id), 'read')
    def get_shares(self, obj):
        if obj.author_id != self.context['request'].user.id:
            return []
        return [{'user':s.user_id,'permission':s.permission} for s in obj.shares.all()]
    def validate_family(self, family):
        if not Membership.objects.filter(family=family,user=self.context['request'].user).exists() or family.status != Family.Status.ACTIVE:
            raise ValidationError('invalid_family')
        if self.instance and self.instance.family_id != family.id:
            raise ValidationError('immutable_family')
        return family

class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get','post','patch','delete','head','options']
    def get_queryset(self):
        user = self.request.user
        qs = Note.objects.filter(family__status=Family.Status.ACTIVE, family__memberships__user=user).filter(Q(author=user)|Q(shares__user=user)).distinct().select_related('author').prefetch_related('shares')
        if self.request.query_params.get('family'):
            try:
                family_id = uuid.UUID(self.request.query_params['family'])
            except (ValueError, TypeError):
                raise ValidationError('invalid_family')
            qs = qs.filter(family_id=family_id)
        query = self.request.query_params.get('search','')[:200]
        if query:
            qs = qs.filter(Q(title__icontains=query)|Q(body__icontains=query))
        return qs
    def perform_create(self, serializer):
        with transaction.atomic():
            note = serializer.save(author=self.request.user)
            self.snapshot(note)
    def snapshot(self, note):
        NoteRevision.objects.create(note=note,actor=self.request.user,version=note.version,title=note.title,body=note.body,drawing=note.drawing)
        stale = list(note.revisions.order_by('-version').values_list('id',flat=True)[20:])
        NoteRevision.objects.filter(id__in=stale).delete()
    def may_edit(self, note):
        if note.author_id != self.request.user.id and not note.shares.filter(user=self.request.user,permission='edit').exists():
            raise PermissionDenied('read_only')
    def partial_update(self, request, *args, **kwargs):
        visible = self.get_object()
        with transaction.atomic():
            note = Note.objects.select_for_update().get(pk=visible.pk)
            # Recheck visibility/permission under lock, including revoked shares.
            if note.author_id != request.user.id and not note.shares.filter(user=request.user).exists():
                raise PermissionDenied('access_revoked')
            self.may_edit(note)
            if isinstance(request.data.get('version'), bool) or not isinstance(request.data.get('version'), int) or request.data.get('version') != note.version:
                return Response({'detail':'note_conflict','current':self.get_serializer(note).data}, status=409)
            serializer = self.get_serializer(note,data=request.data,partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save(version=note.version+1)
            self.snapshot(note)
            return Response(serializer.data)
    def perform_destroy(self, instance):
        if instance.author_id != self.request.user.id:
            raise PermissionDenied('owner_only')
        instance.delete()
    @action(detail=True,methods=['post'])
    def sharing(self, request, pk=None):
        visible = self.get_object()
        with transaction.atomic():
            note = Note.objects.select_for_update().get(pk=visible.pk)
            if note.author_id != request.user.id:
                raise PermissionDenied('owner_only')
            if isinstance(request.data.get('version'), bool) or not isinstance(request.data.get('version'), int) or request.data.get('version') != note.version:
                return Response({'detail':'note_conflict'},status=409)
            shares = request.data.get('shares')
            if not isinstance(shares,list) or len(shares)>50:
                raise ValidationError('invalid_shares')
            cleaned = {}
            for share in shares:
                if not isinstance(share,dict) or share.get('permission') not in ['read','edit']:
                    raise ValidationError('invalid_permission')
                uid = share.get('user')
                if isinstance(uid,bool) or not isinstance(uid,int) or uid == note.author_id or not Membership.objects.filter(family=note.family,user_id=uid).exists():
                    raise ValidationError('invalid_member')
                cleaned[uid] = share['permission']
            note.shares.all().delete()
            NoteShare.objects.bulk_create([NoteShare(note=note,user_id=uid,permission=permission) for uid,permission in cleaned.items()])
            note.version += 1
            note.save(update_fields=['version','updated_at'])
            self.snapshot(note)
            return Response(self.get_serializer(note).data)
    @action(detail=True,methods=['get'])
    def history(self, request, pk=None):
        note = self.get_object()
        # A newly invited collaborator cannot inspect content predating their invitation.
        if note.author_id != request.user.id:
            raise PermissionDenied('owner_only')
        rows = note.revisions.all()
        page = self.paginate_queryset(rows)
        data = [{'id':r.id,'version':r.version,'title':r.title,'body':r.body,'drawing':r.drawing,'created_at':r.created_at,'actor':r.actor_id} for r in (page if page is not None else rows)]
        return self.get_paginated_response(data) if page is not None else Response(data)
