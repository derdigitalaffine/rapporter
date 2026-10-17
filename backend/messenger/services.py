"""Personal conversation operations. Every write rechecks consent under row locks."""
import uuid
import hashlib
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from auth_identity.models import EmailIdentity
from family.models import Membership
from .access import WRITER_ROLES, family_writer, friendship_access, friendship_for, is_blocked, membership, preferences, require_writer, shared_chat_family, visible_messages
from .models import ChatBlock, ChatMessage, ChatReaction, ContactInvitation, Conversation, ConversationMember, Friendship

REACTIONS = {"👍", "❤️", "😂", "😮", "😢", "🙏", "🎉", "👎"}
SYSTEM_USERNAME = "__familyos_system__"


def system_user():
    User = get_user_model()
    row, created = User.objects.get_or_create(username=SYSTEM_USERNAME, defaults={"is_active": False, "first_name": "System"})
    if created:
        row.set_unusable_password()
        row.save(update_fields=["password"])
    return row


def _join(conversation, user, inviter, *, state="active", label=None):
    return ConversationMember.objects.create(conversation=conversation, user=user, invited_by=inviter, label=(label or preferences(user).display_name)[:80], state=state, joined_at=timezone.now() if state == "active" else None)


def _family_member_rows(family_id):
    return list(
        Membership.objects.filter(
            family_id=family_id,
            family__status="active",
            role__in=WRITER_ROLES,
            user__is_active=True,
        ).select_related("user").order_by("created_at")
    )


def _sync_family_channel(family, channel, rows, actor, now):
    title = family.name[:100] if channel == Conversation.Channel.FAMILY else "System"
    creator = actor if channel == Conversation.Channel.FAMILY else system_user()
    conv, _ = Conversation.objects.select_for_update().get_or_create(
        family=family,
        channel=channel,
        defaults={"kind": "group", "title": title, "created_by": creator},
    )
    if conv.title != title:
        conv.title = title
        conv.save(update_fields=["title", "updated_at"])
    desired = {row.user_id: row for row in rows}
    existing = {row.user_id: row for row in ConversationMember.objects.select_for_update().filter(conversation=conv)}
    for user_id, row in desired.items():
        label = (row.display_name or preferences(row.user).display_name)[:80]
        participant = existing.get(user_id)
        if participant:
            fields = []
            if participant.state != "active":
                participant.state = "active"
                participant.joined_at = now
                participant.left_at = None
                fields.extend(["state", "joined_at", "left_at"])
            if participant.label != label:
                participant.label = label
                fields.append("label")
            if fields:
                participant.save(update_fields=[*fields, "updated_at"])
        else:
            _join(conv, row.user, creator, label=label)
    for user_id, participant in existing.items():
        if user_id not in desired and participant.state != "left":
            participant.state = "left"
            participant.left_at = now
            participant.typing_until = None
            participant.save(update_fields=["state", "left_at", "typing_until", "updated_at"])
    return conv


@transaction.atomic
def sync_family_groups(user):
    """Ensure every active chat-capable family has canonical Family and System channels."""
    require_writer(user)
    own = list(Membership.objects.filter(user=user, family__status="active", role__in=WRITER_ROLES).select_related("family").order_by("created_at"))
    now = timezone.now()
    synced = []
    for own_member in own:
        rows = _family_member_rows(own_member.family_id)
        if not rows:
            continue
        synced.append(_sync_family_channel(own_member.family, Conversation.Channel.FAMILY, rows, user, now))
        synced.append(_sync_family_channel(own_member.family, Conversation.Channel.SYSTEM, rows, user, now))
    return synced


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
def family_direct_conversation(user, target_user_id):
    require_writer(user)
    try:
        target_user_id = int(target_user_id)
    except (TypeError, ValueError):
        raise Http404 from None
    if target_user_id == user.pk or is_blocked(user.pk, target_user_id) or not shared_chat_family(user.pk, target_user_id):
        raise Http404
    users = {row.pk: row for row in get_user_model().objects.select_for_update(no_key=True).filter(pk__in=(user.pk, target_user_id)).order_by("pk")}
    target = users.get(target_user_id)
    if not target or not family_writer(target):
        raise Http404
    low, high = sorted((user.pk, target_user_id))
    friend = Friendship.objects.select_for_update().filter(low_user_id=low, high_user_id=high).first()
    if friend:
        if not friend.active:
            friend.active = True
            friend.family_derived = True
            friend.save(update_fields=["active", "family_derived", "updated_at"])
    else:
        friend = Friendship.objects.create(low_user_id=low, high_user_id=high, family_derived=True)
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
    conv = Conversation.objects.select_for_update().filter(pk=conversation_id, kind="group", family__isnull=True).first()
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
    friend = Friendship.objects.filter(pk=friendship_id).filter(Q(low_user=user) | Q(high_user=user)).first()
    if not friend:
        raise Http404
    list(get_user_model().objects.select_for_update(no_key=True).filter(pk__in=(friend.low_user_id, friend.high_user_id)).order_by("pk"))
    friend = Friendship.objects.select_for_update().get(pk=friend.pk)
    friend.active = False
    friend.save(update_fields=["active", "updated_at"])
    other = friend.other_id(user.pk)
    if block:
        ChatBlock.objects.get_or_create(blocker=user, blocked_id=other)
    identities = dict(EmailIdentity.objects.filter(user_id__in=(user.pk, other), kind="primary").values_list("user_id", "email_normalized"))
    invite_scope = Q(sender_id=user.pk, email=identities.get(other, "")) | Q(sender_id=other, email=identities.get(user.pk, ""))
    cutoff = friend.updated_at
    def revoke_pending():
        with transaction.atomic():
            rows = list(ContactInvitation.objects.select_for_update().filter(invite_scope, status="pending", created_at__lte=cutoff).order_by("pk"))
            ContactInvitation.objects.filter(pk__in=[row.pk for row in rows]).update(status="revoked")
    transaction.on_commit(revoke_pending)
    ConversationMember.objects.filter(conversation__friendship=friend).update(typing_until=None)
    return friend


def _locked_member(user, conversation_id):
    scope = Conversation.objects.filter(pk=conversation_id).first()
    if scope and scope.friendship_id:
        friendship_access(user, scope.friendship_id, lock=True, allow_family=True)
    conv = Conversation.objects.select_for_update().filter(pk=conversation_id).first()
    if not conv:
        raise Http404
    if conv.channel == Conversation.Channel.SYSTEM:
        raise PermissionDenied({"code": "system_chat_read_only"})
    member = membership(user, conv.pk, write=True, lock=True)
    return conv, member


def _revision(conv):
    conv.revision += 1
    conv.save(update_fields=["revision", "updated_at"])
    return conv.revision


def validate_location(value):
    """One static point, no arbitrary metadata or external URLs."""
    import math
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"latitude", "longitude", "accuracy"}:
        raise ValidationError({"code": "invalid_location"})
    limits = {"latitude": (-90, 90), "longitude": (-180, 180), "accuracy": (0, 100000)}
    result = {}
    for key, (low, high) in limits.items():
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not low <= number <= high:
            raise ValidationError({"code": "invalid_location"})
        result[key] = round(float(number), 5 if key != "accuracy" else 1)
    return result


@transaction.atomic
def send_message(user, conversation_id, *, client_id, body, reply_to=None, files=(), location=None):
    conv, member = _locked_member(user, conversation_id)
    location = validate_location(location)
    body = str(body or "").strip()
    if len(body) > 4000 or len(files) > 5 or (not body and not files and location is None):
        raise ValidationError({"code": "invalid_message"})
    from .media import prepare_uploads, save_uploads
    uploads = prepare_uploads(files)
    payload = [body, str(reply_to or ""), [(c.sha256, kind, name) for c, kind, name in uploads]]
    # Preserve pre-migration retry digests for ordinary messages.
    if location is not None:
        payload.append(location)
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()
    previous = conv.messages.filter(sender=user, client_id=client_id).first()
    if previous:
        if previous.payload_digest != digest:
            raise ValidationError({"code": "message_retry_conflict"})
        return previous
    reply = None
    if reply_to:
        reply = visible_messages(member).filter(pk=reply_to, deleted_at__isnull=True).first()
        if not reply:
            raise Http404
    revision = _revision(conv)
    msg = ChatMessage.objects.create(conversation=conv, sender=user, client_id=client_id, body=body, location=location, reply_to=reply, sequence=revision, event_sequence=revision, payload_digest=digest)
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
            msg.location = None
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
    if not Conversation.objects.select_for_update().filter(pk=conversation_id).exists():
        raise Http404
    member = membership(user, conversation_id, lock=True)
    if member.state != "active":
        raise Http404
    last = visible_messages(member).filter(sequence__lte=sequence).order_by("-sequence").first()
    if last and last.sequence > member.last_read_sequence:
        member.last_read_sequence = last.sequence
        member.save(update_fields=["last_read_sequence", "updated_at"])
    latest = visible_messages(member).order_by("-sequence").first()
    if latest and member.last_read_sequence >= latest.sequence:
        from notifications.models import Notification
        from notifications.services import sync_launcher_badge
        updated = Notification.objects.filter(recipient_user=user, event_type="chat.message", resource_url=f"/?page=inbox&chat={conversation_id}", read_at__isnull=True).update(read_at=timezone.now())
        if updated:
            sync_launcher_badge(user)
    return member
