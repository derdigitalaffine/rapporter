from rest_framework import serializers
from rest_framework.response import Response

from .board_models import PinComment, PinInteractionState
from .board_views import BoardSerializer, BoardViewSet
from .domain_notifications import notify_domain_event
from .pin_interactions import (
    PinInteractionMixin,
    build_pin_interaction_summaries,
    interaction_summary_for_pin,
)
from .pin_visibility import resolve_pin_page_visibility, visible_pin_memberships


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

    def _notify_comment_created(self, pin, comment, mentions):
        """Revalidate the effective audience at delivery time; activity never widens ACL."""
        visible = list(visible_pin_memberships(pin).filter(user__is_active=True).select_related('user'))
        visible_user_ids = {row.user_id for row in visible}
        mentioned_user_ids = {row.user_id for row in mentions if row.user_id in visible_user_ids}
        url = f'/?page=board&post={pin.id}&comment={comment.id}'
        if mentioned_user_ids:
            notify_domain_event(
                pin.family,
                'pin.mention',
                actor=self.request.user,
                context={'pin_id': pin.id, 'comment_id': comment.id},
                target_users=mentioned_user_ids,
                url=url,
            )

        follower_user_ids = set(
            PinComment.objects.filter(pin=pin, deleted_at__isnull=True)
            .exclude(author_id__isnull=True)
            .values_list('author_id', flat=True)
        )
        if pin.author_id:
            follower_user_ids.add(pin.author_id)
        follower_user_ids.discard(self.request.user.id)
        follower_user_ids -= mentioned_user_ids
        recipients = [row for row in visible if row.user_id in follower_user_ids]
        if not recipients:
            return
        muted_ids = set(
            PinInteractionState.objects.filter(
                pin=pin,
                membership__in=recipients,
                muted=True,
            ).values_list('membership_id', flat=True)
        )
        target_users = [row.user_id for row in recipients if row.id not in muted_ids]
        if target_users:
            notify_domain_event(
                pin.family,
                'pin.comment',
                actor=self.request.user,
                context={'pin_id': pin.id, 'comment_id': comment.id},
                target_users=target_users,
                url=url,
            )
