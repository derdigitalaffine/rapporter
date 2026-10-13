from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from auth_identity.models import EmailIdentity
from family.models import Membership
from .models import ChatBlock, ChatPreference, Conversation, ConversationMember, Friendship

WRITER_ROLES = (Membership.Role.OWNER, Membership.Role.ADULT, Membership.Role.TEEN)


def preferences(user):
    name = user.get_short_name() or Membership.objects.filter(user=user).exclude(display_name="").values_list("display_name", flat=True).first() or user.get_username()
    return ChatPreference.objects.get_or_create(user=user, defaults={"display_name": name[:80]})[0]


def active_chat_user(user):
    return bool(user and user.is_active and not (getattr(user, "is_superadmin", False) or user.is_superuser))


def family_writer(user):
    if not active_chat_user(user):
        return False
    return Membership.objects.filter(user=user, role__in=WRITER_ROLES, family__status="active").exists()


def external_chat_eligible(user):
    if not active_chat_user(user):
        return False
    verified = EmailIdentity.objects.filter(user=user, kind="primary", verified_at__isnull=False).exists()
    if not verified:
        return False
    # External friendships retain the pre-family-channel identity/role fence.
    # A suspended tenant disables family content, not a verified personal chat;
    # a child/guest-only membership never gains access through personal_account.
    members = Membership.objects.filter(user=user)
    if members.exists():
        return members.filter(role__in=WRITER_ROLES).exists()
    return ChatPreference.objects.filter(user=user, personal_account=True).exists()


def eligible(user):
    return family_writer(user) or external_chat_eligible(user)


def require_writer(user):
    if not eligible(user):
        raise PermissionDenied({"code": "chat_account_unavailable", "detail": "Für Chats benötigst du eine berechtigte Familienrolle oder ein bestätigtes persönliches Chat-Konto."})


def blocked_ids(user):
    rows = ChatBlock.objects.filter(Q(blocker=user) | Q(blocked=user)).values_list("blocker_id", "blocked_id")
    return {other if own == user.pk else own for own, other in rows}


def is_blocked(one, other):
    return ChatBlock.objects.filter(Q(blocker_id=one, blocked_id=other) | Q(blocker_id=other, blocked_id=one)).exists()


def shared_chat_family(one, other):
    try:
        one, other = int(one), int(other)
    except (TypeError, ValueError):
        return False
    if one == other:
        return False
    return Membership.objects.filter(
        user_id=one,
        role__in=WRITER_ROLES,
        family__status="active",
        family__memberships__user_id=other,
        family__memberships__role__in=WRITER_ROLES,
    ).exists()


def friendship_for(one, other, *, lock=False, allow_family=False):
    low, high = sorted((int(one), int(other)))
    rows = Friendship.objects.select_related("low_user", "high_user")
    if lock:
        rows = rows.select_for_update(of=("self",))
    row = rows.filter(low_user_id=low, high_user_id=high, active=True).first()
    if not row or is_blocked(low, high):
        raise Http404
    if row.family_derived:
        if not allow_family or not family_writer(row.low_user) or not family_writer(row.high_user) or not shared_chat_family(low, high):
            raise Http404
    elif not external_chat_eligible(row.low_user) or not external_chat_eligible(row.high_user):
        raise Http404
    return row


def friendship_access(user, friendship_id, *, lock=False, allow_family=False):
    rows = Friendship.objects.select_related("low_user", "high_user")
    if lock:
        rows = rows.select_for_update(of=("self",))
    row = rows.filter(pk=friendship_id, active=True).filter(Q(low_user=user) | Q(high_user=user)).first()
    if not row or is_blocked(row.low_user_id, row.high_user_id):
        raise Http404
    if row.family_derived:
        if not allow_family or not family_writer(row.low_user) or not family_writer(row.high_user) or not shared_chat_family(row.low_user_id, row.high_user_id):
            raise Http404
    elif not external_chat_eligible(row.low_user) or not external_chat_eligible(row.high_user):
        raise Http404
    return row


def membership(user, conversation_id, *, write=False, lock=False):
    require_writer(user)
    rows = ConversationMember.objects.select_related("conversation", "conversation__friendship", "conversation__family", "user", "invited_by")
    if lock:
        rows = rows.select_for_update(of=("self",))
    member = rows.filter(user=user, conversation_id=conversation_id).first()
    if not member or not user.is_active:
        raise Http404
    if member.conversation.family_id and not Membership.objects.filter(user=user, family_id=member.conversation.family_id, role__in=WRITER_ROLES, family__status="active").exists():
        raise Http404
    if write:
        require_writer(user)
        if member.state != "active":
            raise PermissionDenied({"code": "chat_not_active"})
        if member.conversation.channel == Conversation.Channel.SYSTEM:
            raise PermissionDenied({"code": "system_chat_read_only"})
        if member.conversation.kind == "direct":
            friendship_access(user, member.conversation.friendship_id, lock=lock, allow_family=True)
    return member


def visible_messages(member):
    rows = member.conversation.messages.all().exclude(sender_id__in=blocked_ids(member.user))
    if member.state == "invited" or not member.joined_at:
        return rows.none()
    rows = rows.filter(created_at__gte=member.joined_at)
    if member.left_at:
        rows = rows.filter(created_at__lte=member.left_at, updated_at__lte=member.left_at)
    return rows


def can_send(member):
    try:
        membership(member.user, member.conversation_id, write=True)
        return True
    except (Http404, PermissionDenied):
        return False


def profile_payload(user, *, label=None):
    return {"id": user.pk, "display_name": label or preferences(user).display_name, "avatar_url": f"/api/chat/avatars/{user.pk}/"}
