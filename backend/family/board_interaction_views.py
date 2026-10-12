from rest_framework import serializers
from rest_framework.response import Response

from .board_views import BoardSerializer, BoardViewSet
from .pin_interactions import (
    PinInteractionMixin,
    build_pin_interaction_summaries,
    interaction_summary_for_pin,
)
from .pin_visibility import resolve_pin_page_visibility


EMPTY_INTERACTION = {
    'comment_count': 0,
    'has_unread_comments': False,
    'reactions': [],
    'can_interact': False,
    'muted': False,
}


class InteractiveBoardSerializer(BoardSerializer):
    interaction = serializers.SerializerMethodField()

    class Meta(BoardSerializer.Meta):
        fields = [*BoardSerializer.Meta.fields, 'interaction']

    def get_interaction(self, obj):
        if self._effective_scope_for(obj) == 'none':
            return dict(EMPTY_INTERACTION)
        summaries = self.context.get('interaction_summaries')
        if summaries is not None:
            return summaries.get(obj.id, dict(EMPTY_INTERACTION))
        return interaction_summary_for_pin(obj, self.context['request'].user) or dict(EMPTY_INTERACTION)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get('can_interact') is False:
            data['interaction'] = dict(EMPTY_INTERACTION)
        return data


class InteractiveBoardViewSet(PinInteractionMixin, BoardViewSet):
    serializer_class = InteractiveBoardSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        context = self.get_serializer_context()
        context['pin_targets'], context['_pin_effective_scope_cache'] = resolve_pin_page_visibility(rows, request.user)
        visible_ids = {
            pin_id
            for pin_id, scope in context['_pin_effective_scope_cache'].items()
            if scope != 'none'
        }
        context['interaction_summaries'] = build_pin_interaction_summaries(
            rows,
            request.user,
            visible_pin_ids=visible_ids,
        )
        serializer = self.get_serializer(rows, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
