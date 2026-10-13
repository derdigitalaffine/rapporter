"""Personal conversation operations. Every write rechecks consent under row locks."""
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from auth_identity.models import EmailIdentity
from .access import friendship_access, friendship_for, is_blocked, membership, preferences, require_writer, visible_messages
from .models import ChatBlock, ChatMessage, ChatReaction, ContactInvitation, Conversation, ConversationMember, Friendship

REACTIONS = {"👍", "❤️", "😂", "😮", "😢", "🙏", "🎉", "👎"}


def _join(conversation, user, inviter, *, state="active"):
    return ConversationMember.objects.create(conversation=conversation, user=user, invited_by=inviter, label=preferences(user).display_name, state=state, joined_at=timezone.now() if state == "active" else None)


@transaction.atomic
def direct_conversation(user, friendship_id):
    require_writer(user)
    friend = friendship_access(user, friendship_id, lock=True)
    conv, created = Conversation.objects.get_or_create(friendship=friend, defaults={"kind": "direct", "created_by": user})
    if created:
        _join(conv, friend.low_user, user)
        _join(conv, friend.high_user, user)
    return membership(user, conv.pk)


@transaction.atomic
def create_group(user, title, friend_ids):
    require_writer(user)
    title = str(title or "").strip()
    if not title or len(title) > 100 or not isinstance(friend_ids, list) or not 1 <= len(friend_ids) <= 19:
        raise ValidationError({"code": "invalid_group"})
    friends = [friendship_access(user, key, lock=True) for key in sorted(set(map(str, friend_ids)))]
    conv = Conversation.objects.create(kind="group", title=title, created_by=user)
    _join(conv, user, user)
    for friend in friends:
        other = friend.high_user if friend.low_user_id == user.pk else friend.low_user
        require_writer(other)
        _join(conv, other, user, state="invited")
    return membership(user, conv.pk)


@transaction.atomic
def group_action(user, conversation_id, action):
    conv = Conversation.objects.select_for_update().filter(pk=conversation_id, kind="group").first()
    if not conv:
        raise Http404
    member = membership(user, conv.pk, lock=True)
    require_writer(user)
    if action == "join" and member.state == "invited":
        friendship_for(user.pk, member.invited_by_id, lock=True)
        member.state, member.joined_at, member.left_at = "active", timezone.now(), None
    elif action == "leave" and member.state == "active":
        member.state, member.left_at, member.typing_until = "left", timezone.now(), None
    else:
        raise ValidationError({"code": "invalid_group_transition"})
    member.save()
    return member


@transaction.atomic
def change_friendship(user, friendship_id, *, block=False):
    require_writer(user)
    # Same user-pair locks as invitation acceptance prevent reactivation racing a block.
    friend = Friendship.objects.filter(pk=friendship_id).filter(Q(low_user=user) | Q(high_user=user)).first()
    if not friend:
        raise Http404
    list(get_user_model().objects.select_for_update().filter(pk__in=(friend.low_user_id, friend.high_user_id)).order_by("pk"))
    friend = Friendship.objects.select_for_update().get(pk=friend.pk)
    friend.active = False
    friend.save(update_fields=["active", "updated_at"])
    other = friend.other_id(user.pk)
    if block:
        ChatBlock.objects.get_or_create(blocker=user, blocked_id=other)
    identities = dict(EmailIdentity.objects.filter(user_id__in=(user.pk, other), kind="primary").values_list("user_id", "email_normalized"))
    ContactInvitation.objects.filter(Q(sender_id=user.pk, email=identities.get(other, "")) | Q(sender_id=other, email=identities.get(user.pk, "")), status="pending").update(status="revoked")
    ConversationMember.objects.filter(conversation__friendship=friend).update(typing_until=None)
    return friend


def _locked_member(user, conversation_id):
    scope = Conversation.objects.filter(pk=conversation_id).first()
    if scope and scope.friendship_id:
        friendship_access(user, scope.friendship_id, lock=True)
    conv = Conversation.objects.select_for_update().filter(pk=conversation_id).first()
    if not conv:
        raise Http404
    member = membership(user, conv.pk, write=True, lock=True)
    return conv, member


def _revision(conv):
    conv.revision += 1
    conv.save(update_fields=["revision", "updated_at"])
    return conv.revision


@transaction.atomic
def send_message(user, conversation_id, *, client_id, body, reply_to=None, files=()):
    conv, member = _locked_member(user, conversation_id)
    body = str(body or "").strip()
    if len(body) > 4000 or len(files) > 5 or (not body and not files):
        raise ValidationError({"code": "invalid_message"})
    previous = conv.messages.filter(sender=user, client_id=client_id).first()
    if previous:
        if previous.body != body or str(previous.reply_to_id or "") != str(reply_to or ""):
            raise ValidationError({"code": "message_retry_conflict"})
        return previous
    reply = None
    if reply_to:
        reply = visible_messages(member).filter(pk=reply_to, deleted_at__isnull=True).first()
        if not reply:
            raise Http404
    from .media import prepare_uploads, save_uploads
    uploads = prepare_uploads(files)
    revision = _revision(conv)
    msg = ChatMessage.objects.create(conversation=conv, sender=user, client_id=client_id, body=body, reply_to=reply, sequence=revision, event_sequence=revision)
    save_uploads(msg, uploads)
    member.typing_until = None
    member.save(update_fields=["typing_until", "updated_at"])
    from .delivery import notify_message
    transaction.on_commit(lambda: notify_message(msg.pk))
    return msg


@transaction.atomic
def change_message(user, conversation_id, message_id, *, body=None, delete=False, reaction=None):
    conv, member = _locked_member(user, conversation_id)
    msg = visible_messages(member).filter(pk=message_id).first()
    if not msg:
        raise Http404
    if reaction is not None:
        if msg.deleted_at or reaction not in REACTIONS | {""}:
            raise ValidationError({"code": "invalid_reaction"})
        if reaction:
            ChatReaction.objects.update_or_create(message=msg, user=user, defaults={"emoji": reaction})
        else:
            ChatReaction.objects.filter(message=msg, user=user).delete()
    else:
        if msg.sender_id != user.pk:
            raise PermissionDenied({"code": "sender_required"})
        if delete:
            if msg.deleted_at:
                return msg
            msg.body, msg.deleted_at = "", timezone.now()
            msg.reactions.all().delete()
        else:
            body = str(body or "").strip()
            if msg.deleted_at or not body or len(body) > 4000:
                raise ValidationError({"code": "invalid_message"})
            msg.body, msg.edited_at = body, timezone.now()
    msg.event_sequence = _revision(conv)
    msg.save()
    return msg


@transaction.atomic
def typing(user, conversation_id, active):
    _, member = _locked_member(user, conversation_id)
    member.typing_until = timezone.now() + timedelta(seconds=8) if active else None
    member.save(update_fields=["typing_until", "updated_at"])


@transaction.atomic
def read_messages(user, conversation_id, sequence):
    member = membership(user, conversation_id, lock=True)
    if member.state != "active":
        raise Http404
    last = visible_messages(member).filter(sequence__lte=sequence).order_by("-sequence").first()
    if last and last.sequence > member.last_read_sequence:
        member.last_read_sequence = last.sequence
        member.save(update_fields=["last_read_sequence", "updated_at"])
    return member
