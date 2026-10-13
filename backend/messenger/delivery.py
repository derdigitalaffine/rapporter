"""Generic personal notifications through the canonical notification and push cores."""
from django.http import Http404
from django.utils import timezone

from family.models import Membership
from family.models_features import NotificationPreference
from family.notification_digests import is_quiet
from family.push import send_user_push
from notifications.services import record_personal_notification
from .access import can_send, eligible, is_blocked, preferences
from .models import ChatMessage, ConversationMember


def notify_message(message_id):
    message = ChatMessage.objects.select_related("conversation", "sender").filter(pk=message_id, deleted_at__isnull=True).first()
    if not message:
        return
    for member in ConversationMember.objects.select_related("user", "conversation").filter(conversation=message.conversation, state="active").exclude(user=message.sender):
        if member.muted or member.last_read_sequence >= message.sequence or not eligible(member.user) or is_blocked(member.user_id, message.sender_id) or not can_send(member):
            continue
        pref = preferences(member.user)
        title = "Neue Nachricht" if pref.locale == "de" else "New message"
        url = f"/?page=inbox&chat={message.conversation_id}"
        _, count = record_personal_notification(user=member.user, event_type="chat.message", title=title, resource_url=url)
        if not pref.push_enabled:
            continue
        memberships = list(Membership.objects.filter(user=member.user).select_related("family"))
        existing = {p.membership_id: p for p in NotificationPreference.objects.filter(membership__user=member.user)}
        # Respect every existing family quiet window without leaking that family to peers.
        if any(is_quiet(existing.get(m.pk), m.family) or (existing.get(m.pk) and not existing[m.pk].messages) for m in memberships):
            continue
        send_user_push(member.user, title, "", url, tag=f"chat:{message.conversation_id}", badge_count=count)
