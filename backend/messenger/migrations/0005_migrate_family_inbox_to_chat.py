import uuid

from django.conf import settings
from django.db import migrations


SYSTEM_USERNAME = '__familyos_system__'
WRITER_ROLES = ('owner', 'adult', 'teen')


def _system_user(apps):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(app_label, model_name)
    user, _ = User.objects.get_or_create(
        username=SYSTEM_USERNAME,
        defaults={'is_active': False, 'first_name': 'System', 'password': '!'},
    )
    return user


def _body(item):
    if item.withdrawn_at:
        return 'Diese Mitteilung wurde zurückgezogen.'
    title = (item.title or '').strip()
    body = (item.body or '').strip()
    text = body if not title or title == body else f'{title}\n\n{body}'.strip()
    if item.important:
        text = f'⚠️ Wichtig\n\n{text}'.strip()
    return text or title or 'Mitteilung'


def forwards(apps, schema_editor):
    Family = apps.get_model('family', 'Family')
    Membership = apps.get_model('family', 'Membership')
    InboxItem = apps.get_model('family', 'InboxItem')
    InboxReceipt = apps.get_model('family', 'InboxReceipt')
    Conversation = apps.get_model('messenger', 'Conversation')
    ConversationMember = apps.get_model('messenger', 'ConversationMember')
    ChatMessage = apps.get_model('messenger', 'ChatMessage')

    system = _system_user(apps)
    receipts = {}
    for row in InboxReceipt.objects.all().values('item_id', 'membership_id', 'read_at'):
        receipts[(row['item_id'], row['membership_id'])] = row['read_at']

    for family in Family.objects.all().order_by('created_at'):
        members = list(
            Membership.objects.filter(
                family_id=family.pk,
                role__in=WRITER_ROLES,
                user__is_active=True,
            ).select_related('user').order_by('created_at')
        )
        creator = members[0].user if members else system
        channels = {}
        for channel, title, channel_creator in (
            ('family', family.name[:100], creator),
            ('system', 'System', system),
        ):
            conv = Conversation.objects.create(
                kind='group', title=title, created_by=channel_creator,
                family_id=family.pk, channel=channel,
            )
            channels[channel] = conv
            for member in members:
                ConversationMember.objects.create(
                    conversation=conv,
                    user_id=member.user_id,
                    invited_by=channel_creator,
                    state='active',
                    label=(member.display_name or member.user.username)[:80],
                    joined_at=member.created_at,
                )

        channel_items = {'family': [], 'system': []}
        selected = []
        for item in InboxItem.objects.filter(family_id=family.pk).order_by('created_at', 'id'):
            if item.source != 'manual_message':
                channel_items['system'].append(item)
            elif item.audience == 'family':
                channel_items['family'].append(item)
            else:
                selected.append(item)

        for channel, items in channel_items.items():
            conv = channels[channel]
            sequence = 0
            for item in items:
                sequence += 1
                sender_id = item.created_by_id if channel == 'family' and item.created_by_id else system.pk
                message = ChatMessage.objects.create(
                    conversation=conv,
                    sender_id=sender_id,
                    client_id=item.pk if isinstance(item.pk, uuid.UUID) else uuid.uuid5(uuid.NAMESPACE_URL, f'family-inbox:{item.pk}'),
                    sequence=sequence,
                    event_sequence=sequence,
                    payload_digest='',
                    body=_body(item),
                )
                ChatMessage.objects.filter(pk=message.pk).update(created_at=item.created_at, updated_at=item.updated_at)
            if sequence:
                Conversation.objects.filter(pk=conv.pk).update(revision=sequence, updated_at=items[-1].updated_at)

            for member in members:
                cursor = 0
                prefix_read = True
                for seq, item in enumerate(items, start=1):
                    if item.created_at < member.created_at:
                        continue
                    sender_id = item.created_by_id if channel == 'family' and item.created_by_id else system.pk
                    read = sender_id == member.user_id or bool(receipts.get((item.pk, member.pk)))
                    if prefix_read and read:
                        cursor = seq
                    elif not read:
                        prefix_read = False
                ConversationMember.objects.filter(conversation=conv, user_id=member.user_id).update(last_read_sequence=cursor)

        for item in selected:
            recipient_members = list(
                Membership.objects.filter(
                    inbox_receipts__item_id=item.pk,
                    role__in=WRITER_ROLES,
                    user__is_active=True,
                ).select_related('user').distinct()
            )
            participant_ids = {row.user_id for row in recipient_members}
            sender_member = next((row for row in members if row.user_id == item.created_by_id), None)
            if sender_member:
                participant_ids.add(sender_member.user_id)
            selected_members = [row for row in members if row.user_id in participant_ids]
            if not selected_members:
                continue
            selected_creator = sender_member.user if sender_member else system
            conv = Conversation.objects.create(
                kind='group',
                title=(item.title or 'Private Familienmitteilung')[:100],
                created_by=selected_creator,
                channel='custom',
            )
            Conversation.objects.filter(pk=conv.pk).update(created_at=item.created_at, updated_at=item.updated_at)
            for member in selected_members:
                is_read = member.user_id == item.created_by_id or bool(receipts.get((item.pk, member.pk)))
                ConversationMember.objects.create(
                    conversation=conv,
                    user_id=member.user_id,
                    invited_by=selected_creator,
                    state='active',
                    label=(member.display_name or member.user.username)[:80],
                    joined_at=item.created_at,
                    last_read_sequence=1 if is_read else 0,
                )
            message = ChatMessage.objects.create(
                conversation=conv,
                sender_id=item.created_by_id or system.pk,
                client_id=item.pk if isinstance(item.pk, uuid.UUID) else uuid.uuid5(uuid.NAMESPACE_URL, f'family-inbox:{item.pk}'),
                sequence=1,
                event_sequence=1,
                payload_digest='',
                body=_body(item),
            )
            ChatMessage.objects.filter(pk=message.pk).update(created_at=item.created_at, updated_at=item.updated_at)
            Conversation.objects.filter(pk=conv.pk).update(revision=1)


def backwards(apps, schema_editor):
    Conversation = apps.get_model('messenger', 'Conversation')
    Conversation.objects.filter(channel__in=['family', 'system']).delete()
    Conversation.objects.filter(channel='custom', title__isnull=False, friendship__isnull=True).filter(messages__payload_digest='').distinct().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('family', '0227_birthday_age_preferences'),
        ('messenger', '0004_conversation_family'),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
