import uuid
from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Max
from django.http import Http404
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from .board_models import BoardPost, PinComment, PinCommentMention, PinInteractionState, PinReaction
from .domain_notifications import notify_domain_event
from .models import Membership
from .pin_visibility import can_interact_with_pin, visible_pin_memberships


REACTION_LABELS = dict(PinReaction.Key.choices)
REACTION_KEYS = tuple(REACTION_LABELS)


def build_pin_interaction_summaries(pins, user, *, visible_pin_ids=None):
    """Build card summaries in bounded aggregate queries, never one query per Pin."""
    pins = list(pins)
    pin_ids = {pin.id for pin in pins}
    if visible_pin_ids is not None:
        pin_ids &= set(visible_pin_ids)
    if not pin_ids:
        return {}

    family_ids = {pin.family_id for pin in pins if pin.id in pin_ids}
    memberships = {
        row.family_id: row
        for row in Membership.objects.filter(
            family_id__in=family_ids,
            user=user,
            user__is_active=True,
        )
    }
    membership_ids = {row.id for row in memberships.values()}

    comments = PinComment.objects.filter(pin_id__in=pin_ids, deleted_at__isnull=True)
    comment_counts = {
        row['pin_id']: row['count']
        for row in comments.values('pin_id').annotate(count=Count('id'))
    }
    latest_other = {
        row['pin_id']: row['latest']
        for row in comments.exclude(author_id=user.id).values('pin_id').annotate(latest=Max('created_at'))
    }

    reaction_counts = defaultdict(dict)
    for row in (
        PinReaction.objects.filter(pin_id__in=pin_ids, comment__isnull=True)
        .values('pin_id', 'key')
        .annotate(count=Count('id'))
    ):
        reaction_counts[row['pin_id']][row['key']] = row['count']

    mine = {
        row.pin_id: row.key
        for row in PinReaction.objects.filter(
            pin_id__in=pin_ids,
            comment__isnull=True,
            membership_id__in=membership_ids,
        ).only('pin_id', 'key')
    }
    states = {
        row.pin_id: row
        for row in PinInteractionState.objects.filter(
            pin_id__in=pin_ids,
            membership_id__in=membership_ids,
        ).only('pin_id', 'last_seen_comment_at', 'muted')
    }

    result = {}
    for pin in pins:
        if pin.id not in pin_ids or pin.family_id not in memberships:
            continue
        state = states.get(pin.id)
        latest = latest_other.get(pin.id)
        last_seen = state.last_seen_comment_at if state else None
        result[pin.id] = {
            'comment_count': comment_counts.get(pin.id, 0),
            'has_unread_comments': bool(latest and (last_seen is None or latest > last_seen)),
            'reactions': [
                {'key': key, 'count': reaction_counts[pin.id][key], 'mine': mine.get(pin.id) == key}
                for key in REACTION_KEYS
                if reaction_counts[pin.id].get(key)
            ],
            'can_interact': True,
            'muted': bool(state and state.muted),
        }
    return result


def interaction_summary_for_pin(pin, user):
    if not can_interact_with_pin(user, pin):
        return None
    return build_pin_interaction_summaries([pin], user).get(pin.id)


def _reaction_rows_for_comments(comments, membership):
    comment_ids = [row.id for row in comments]
    counts = defaultdict(dict)
    for row in (
        PinReaction.objects.filter(comment_id__in=comment_ids)
        .values('comment_id', 'key')
        .annotate(count=Count('id'))
    ):
        counts[row['comment_id']][row['key']] = row['count']
    mine = {
        row.comment_id: row.key
        for row in PinReaction.objects.filter(comment_id__in=comment_ids, membership=membership).only('comment_id', 'key')
    }
    return counts, mine


def serialize_comments(comments, *, user, membership, pin):
    comments = list(comments)
    author_ids = {row.author_id for row in comments if row.author_id}
    names = {
        row.user_id: (row.display_name or row.user.get_short_name() or row.user.username)
        for row in Membership.objects.filter(family=pin.family, user_id__in=author_ids).select_related('user')
    }
    currently_visible = {
        row.id: row
        for row in visible_pin_memberships(pin).filter(user__is_active=True).select_related('user')
    }
    reaction_counts, mine = _reaction_rows_for_comments(comments, membership)
    is_owner = membership.role == Membership.Role.OWNER
    result = []
    for row in comments:
        deleted = bool(row.deleted_at)
        mentions = []
        if not deleted:
            for mention in row.mentions.all():
                target = currently_visible.get(mention.membership_id)
                if not target:
                    continue
                mentions.append({
                    'id': str(target.id),
                    'name': target.display_name or target.user.get_short_name() or target.user.username,
                })
        result.append({
            'id': str(row.id),
            'body': '' if deleted else row.body,
            'deleted': deleted,
            'author_id': row.author_id,
            'author_name': names.get(row.author_id, 'Ehemaliges Mitglied' if row.author_id else 'Ehemaliges Mitglied'),
            'created_at': row.created_at,
            'updated_at': row.updated_at,
            'edited': bool(not deleted and (row.updated_at - row.created_at).total_seconds() > 0.01),
            'mine': row.author_id == user.id,
            'can_edit': bool(not deleted and row.author_id == user.id),
            'can_delete': bool(not deleted and (row.author_id == user.id or is_owner)),
            'mentions': mentions,
            'reactions': [
                {'key': key, 'count': reaction_counts[row.id][key], 'mine': mine.get(row.id) == key}
                for key in REACTION_KEYS
                if reaction_counts[row.id].get(key)
            ],
        })
    return result


class PinCommentPagination(CursorPagination):
    page_size = 30
    ordering = '-created_at'


class PinInteractionMixin:
    """DRF Board actions backed exclusively by the canonical pin visibility contract."""

    def _interaction_pin(self, pk):
        pin = BoardPost.objects.select_related('family', 'author').filter(pk=pk).first()
        if not pin or not can_interact_with_pin(self.request.user, pin):
            raise Http404
        return pin

    def _interaction_membership(self, pin):
        membership = Membership.objects.filter(
            family=pin.family,
            user=self.request.user,
            user__is_active=True,
        ).first()
        if not membership:
            raise Http404
        return membership

    def _interaction_comment(self, pin, comment_id):
        comment = (
            PinComment.objects.select_related('pin', 'family', 'author')
            .prefetch_related('mentions__membership__user')
            .filter(pk=comment_id, pin=pin, family=pin.family)
            .first()
        )
        if not comment:
            raise Http404
        return comment

    def _validate_reaction_key(self, value):
        if value in (None, ''):
            return None
        value = str(value)
        if value not in REACTION_LABELS:
            raise ValidationError({'key': 'Unbekannte Reaktion.'})
        return value

    def _validate_comment_body(self, value):
        body = str(value or '').strip()
        if not body:
            raise ValidationError({'body': 'Bitte einen Kommentar eingeben.'})
        if len(body) > 2000:
            raise ValidationError({'body': 'Maximal 2000 Zeichen.'})
        return body

    def _validate_mentions(self, pin, values):
        values = values or []
        if not isinstance(values, list):
            raise ValidationError({'mention_membership_ids': 'Ungültige Erwähnungen.'})
        requested = {str(value) for value in values}
        if not requested:
            return []
        allowed = list(
            visible_pin_memberships(pin)
            .filter(id__in=values, user__is_active=True)
            .select_related('user')
        )
        if {str(row.id) for row in allowed} != requested:
            raise ValidationError({'mention_membership_ids': 'Diese Person kann den Pin nicht sehen.'})
        return allowed

    def _record_reaction_activity(self, *, pin, recipient_user, event_type, comment=None):
        if not recipient_user or recipient_user.id == self.request.user.id:
            return
        membership = Membership.objects.filter(family=pin.family, user=recipient_user, user__is_active=True).first()
        if not membership or not can_interact_with_pin(recipient_user, pin):
            return
        try:
            from notifications.services import record_notification
            locale = 'en' if str(pin.family.locale).lower().startswith('en') else 'de'
            title = 'Pinboard reaction' if locale == 'en' else 'Reaktion auf der Pinnwand'
            body = 'New activity on the pinboard.' if locale == 'en' else 'Neue Aktivität auf der Pinnwand.'
            url = f'/?page=board&post={pin.id}' + (f'&comment={comment.id}' if comment else '')
            record_notification(
                recipient=membership,
                event_type=event_type,
                title=title,
                body=body,
                resource_url=url,
            )
        except Exception:
            pass

    def _notify_comment_created(self, pin, comment, mentions):
        mentioned_user_ids = {row.user_id for row in mentions}
        url = f'/?page=board&post={pin.id}&comment={comment.id}'
        if mentions:
            notify_domain_event(
                pin.family,
                'pin.mention',
                actor=self.request.user,
                context={'pin_id': pin.id, 'comment_id': comment.id},
                target_users=[row.user_id for row in mentions],
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
        if not follower_user_ids:
            return

        recipients = list(
            Membership.objects.filter(
                family=pin.family,
                user_id__in=follower_user_ids,
                user__is_active=True,
            ).select_related('user')
        )
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

    def _comment_payload(self, comment, pin, membership):
        comment = (
            PinComment.objects.select_related('author')
            .prefetch_related('mentions__membership__user')
            .get(pk=comment.pk)
        )
        return serialize_comments([comment], user=self.request.user, membership=membership, pin=pin)[0]

    @action(detail=True, methods=['get', 'post'], url_path='comments')
    def comments(self, request, pk=None):
        pin = self._interaction_pin(pk)
        membership = self._interaction_membership(pin)
        if request.method == 'GET':
            queryset = (
                PinComment.objects.filter(pin=pin, family=pin.family)
                .select_related('author')
                .prefetch_related('mentions__membership__user')
                .order_by('-created_at', '-id')
            )
            paginator = PinCommentPagination()
            page = paginator.paginate_queryset(queryset, request, view=self)
            latest = PinComment.objects.filter(pin=pin, deleted_at__isnull=True).aggregate(value=Max('created_at'))['value']
            if latest:
                PinInteractionState.objects.update_or_create(
                    pin=pin,
                    membership=membership,
                    defaults={'last_seen_comment_at': latest},
                )
            return paginator.get_paginated_response(
                serialize_comments(page, user=request.user, membership=membership, pin=pin)
            )

        body = self._validate_comment_body(request.data.get('body'))
        try:
            client_id = uuid.UUID(str(request.data.get('client_id') or ''))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError({'client_id': 'Eine gültige client_id ist erforderlich.'})
        mentions = self._validate_mentions(pin, request.data.get('mention_membership_ids', []))
        with transaction.atomic():
            comment, created = PinComment.objects.get_or_create(
                pin=pin,
                author=request.user,
                client_id=client_id,
                defaults={'family': pin.family, 'body': body},
            )
            if created and mentions:
                PinCommentMention.objects.bulk_create([
                    PinCommentMention(comment=comment, membership=row) for row in mentions
                ])
            PinInteractionState.objects.update_or_create(
                pin=pin,
                membership=membership,
                defaults={'last_seen_comment_at': comment.created_at},
            )
            if created:
                transaction.on_commit(lambda: self._notify_comment_created(pin, comment, mentions))
        payload = self._comment_payload(comment, pin, membership)
        payload['interaction'] = interaction_summary_for_pin(pin, request.user)
        return Response(payload, status=201 if created else 200)

    @action(
        detail=True,
        methods=['patch', 'delete'],
        url_path=r'comments/(?P<comment_id>[0-9a-fA-F-]+)',
    )
    def comment_detail(self, request, pk=None, comment_id=None):
        pin = self._interaction_pin(pk)
        membership = self._interaction_membership(pin)
        comment = self._interaction_comment(pin, comment_id)
        is_owner = membership.role == Membership.Role.OWNER
        if request.method == 'DELETE':
            if comment.deleted_at or (comment.author_id != request.user.id and not is_owner):
                raise Http404
            moderated = comment.author_id != request.user.id
            with transaction.atomic():
                comment.body = ''
                comment.deleted_at = timezone.now()
                comment.save(update_fields=['body', 'deleted_at', 'updated_at'])
                comment.mentions.all().delete()
                comment.reactions.all().delete()
                if moderated:
                    def audit():
                        try:
                            from telemetry.service import try_record_audit_event
                            try_record_audit_event(
                                'pin.comment.moderated',
                                actor=request.user,
                                actor_class='superadmin' if request.user.is_superuser else 'user',
                                family=pin.family,
                                target_type='pin_comment',
                                target_id=str(comment.id),
                                metadata={},
                            )
                        except Exception:
                            pass
                    transaction.on_commit(audit)
            return Response({'comment': self._comment_payload(comment, pin, membership), 'interaction': interaction_summary_for_pin(pin, request.user)})

        if comment.deleted_at or comment.author_id != request.user.id:
            raise Http404
        body = self._validate_comment_body(request.data.get('body'))
        mention_values = request.data.get('mention_membership_ids', None)
        mentions = None if mention_values is None else self._validate_mentions(pin, mention_values)
        comment.body = body
        comment.save(update_fields=['body', 'updated_at'])
        if mentions is not None:
            comment.mentions.all().delete()
            PinCommentMention.objects.bulk_create([
                PinCommentMention(comment=comment, membership=row) for row in mentions
            ])
        return Response(self._comment_payload(comment, pin, membership))

    @action(detail=True, methods=['put'], url_path='reaction')
    def reaction(self, request, pk=None):
        pin = self._interaction_pin(pk)
        membership = self._interaction_membership(pin)
        key = self._validate_reaction_key(request.data.get('key'))
        changed = False
        with transaction.atomic():
            Membership.objects.select_for_update().get(pk=membership.pk)
            current = PinReaction.objects.select_for_update().filter(
                pin=pin,
                membership=membership,
                comment__isnull=True,
            ).first()
            if key is None:
                if current:
                    current.delete()
                    changed = True
            elif current:
                if current.key != key:
                    current.key = key
                    current.save(update_fields=['key', 'updated_at'])
                    changed = True
            else:
                PinReaction.objects.create(pin=pin, membership=membership, key=key)
                changed = True
            if changed and key and pin.author_id:
                transaction.on_commit(lambda: self._record_reaction_activity(
                    pin=pin,
                    recipient_user=pin.author,
                    event_type='pin.reaction',
                ))
        return Response(interaction_summary_for_pin(pin, request.user))

    @action(
        detail=True,
        methods=['put'],
        url_path=r'comments/(?P<comment_id>[0-9a-fA-F-]+)/reaction',
    )
    def comment_reaction(self, request, pk=None, comment_id=None):
        pin = self._interaction_pin(pk)
        membership = self._interaction_membership(pin)
        comment = self._interaction_comment(pin, comment_id)
        if comment.deleted_at:
            raise Http404
        key = self._validate_reaction_key(request.data.get('key'))
        changed = False
        with transaction.atomic():
            Membership.objects.select_for_update().get(pk=membership.pk)
            current = PinReaction.objects.select_for_update().filter(
                pin=pin,
                comment=comment,
                membership=membership,
            ).first()
            if key is None:
                if current:
                    current.delete()
                    changed = True
            elif current:
                if current.key != key:
                    current.key = key
                    current.save(update_fields=['key', 'updated_at'])
                    changed = True
            else:
                PinReaction.objects.create(pin=pin, comment=comment, membership=membership, key=key)
                changed = True
            if changed and key and comment.author_id:
                transaction.on_commit(lambda: self._record_reaction_activity(
                    pin=pin,
                    recipient_user=comment.author,
                    event_type='pin.reaction',
                    comment=comment,
                ))
        return Response(self._comment_payload(comment, pin, membership))

    @action(detail=True, methods=['get'], url_path='mention-targets')
    def mention_targets(self, request, pk=None):
        pin = self._interaction_pin(pk)
        rows = visible_pin_memberships(pin).filter(user__is_active=True).select_related('user').order_by('display_name', 'id')
        return Response([
            {
                'id': str(row.id),
                'name': row.display_name or row.user.get_short_name() or row.user.username,
            }
            for row in rows
        ])

    @action(detail=True, methods=['post'], url_path='seen')
    def seen(self, request, pk=None):
        pin = self._interaction_pin(pk)
        membership = self._interaction_membership(pin)
        latest = PinComment.objects.filter(pin=pin, deleted_at__isnull=True).aggregate(value=Max('created_at'))['value']
        PinInteractionState.objects.update_or_create(
            pin=pin,
            membership=membership,
            defaults={'last_seen_comment_at': latest or timezone.now()},
        )
        return Response(interaction_summary_for_pin(pin, request.user))

    @action(detail=True, methods=['post'], url_path='mute')
    def mute(self, request, pk=None):
        pin = self._interaction_pin(pk)
        membership = self._interaction_membership(pin)
        muted = request.data.get('muted', True)
        if not isinstance(muted, bool):
            raise ValidationError({'muted': 'muted muss true oder false sein.'})
        state, _ = PinInteractionState.objects.get_or_create(pin=pin, membership=membership)
        state.muted = muted
        state.save(update_fields=['muted', 'updated_at'])
        return Response(interaction_summary_for_pin(pin, request.user))
