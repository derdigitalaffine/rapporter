import uuid

from django.db import transaction
from django.utils import timezone

from family.models import Membership
from .access import WRITER_ROLES
from .models import ChatMessage, Conversation, ConversationMember
from .services import sync_family_groups, system_user


def _message_body(item):
    if item.withdrawn_at:
        return 'Diese Mitteilung wurde zurückgezogen.'
    title = (item.title or '').strip()
    body = (item.body or '').strip()
    text = body if not title or title == body else f'{title}\n\n{body}'.strip()
    if item.important:
        text = f'⚠️ Wichtig\n\n{text}'.strip()
    return text or title or 'Mitteilung'


def _actor_for(item):
    if item.created_by_id and Membership.objects.filter(
        family_id=item.family_id,
        user_id=item.created_by_id,
        role__in=WRITER_ROLES,
        family__status='active',
        user__is_active=True,
    ).exists():
        return item.created_by
    row = Membership.objects.filter(
        family_id=item.family_id,
        role__in=WRITER_ROLES,
        family__status='active',
        user__is_active=True,
    ).select_related('user').order_by('created_at').first()
    return row.user if row else None


def mirror_inbox_item(item):
    """Compatibility bridge until legacy InboxItem producers are retired."""
    if ChatMessage.objects.filter(client_id=item.pk).exists():
        return
    actor = _actor_for(item)
    if not actor:
        return
    sync_family_groups(actor)
    if item.source != 'manual_message':
        conv = Conversation.objects.get(family_id=item.family_id, channel=Conversation.Channel.SYSTEM)
        sender = system_user()
    elif item.audience == 'family':
        conv = Conversation.objects.get(family_id=item.family_id, channel=Conversation.Channel.FAMILY)
        sender = item.created_by or system_user()
    else:
        receipt_ids = list(item.receipts.values_list('membership_id', flat=True))
        members = list(Membership.objects.filter(id__in=receipt_ids, role__in=WRITER_ROLES, user__is_active=True).select_related('user'))
        if item.created_by_id:
            sender_member = Membership.objects.filter(family_id=item.family_id, user_id=item.created_by_id, role__in=WRITER_ROLES, user__is_active=True).select_related('user').first()
            if sender_member and all(row.user_id != sender_member.user_id for row in members):
                members.append(sender_member)
        if not members:
            return
        sender = item.created_by or system_user()
        conv = Conversation.objects.create(kind='group', channel=Conversation.Channel.CUSTOM, title=(item.title or 'Private Familienmitteilung')[:100], created_by=sender)
        for row in members:
            ConversationMember.objects.create(
                conversation=conv,
                user=row.user,
                invited_by=sender,
                state='active',
                label=(row.display_name or row.user.get_username())[:80],
                joined_at=item.created_at,
                last_read_sequence=1 if row.user_id == item.created_by_id or item.receipts.filter(membership_id=row.pk, read_at__isnull=False).exists() else 0,
            )
    with transaction.atomic():
        conv = Conversation.objects.select_for_update().get(pk=conv.pk)
        if ChatMessage.objects.filter(client_id=item.pk).exists():
            return
        sequence = conv.revision + 1
        conv.revision = sequence
        conv.save(update_fields=['revision', 'updated_at'])
        message = ChatMessage.objects.create(
            conversation=conv,
            sender=sender,
            client_id=item.pk if isinstance(item.pk, uuid.UUID) else uuid.uuid5(uuid.NAMESPACE_URL, f'family-inbox:{item.pk}'),
            sequence=sequence,
            event_sequence=sequence,
            payload_digest='',
            body=_message_body(item),
        )
        ChatMessage.objects.filter(pk=message.pk).update(created_at=item.created_at, updated_at=item.updated_at)


def schedule_inbox_mirror(item_id):
    def run():
        from family.models import InboxItem
        item = InboxItem.objects.select_related('family', 'created_by').prefetch_related('receipts').filter(pk=item_id).first()
        if item:
            mirror_inbox_item(item)
    transaction.on_commit(run)
