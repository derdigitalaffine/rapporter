from django.utils import timezone

from .access import blocked_ids, can_send, profile_payload, visible_messages
from .models import ChatPreference, Conversation


def message_payload(message, member):
    deleted = bool(message.deleted_at)
    if not hasattr(member, "_payload_peers"):
        member._payload_peers = {p.user_id: p for p in member.conversation.participants.all()}
        member._payload_blocked = blocked_ids(member.user)
    peers = member._payload_peers
    sender = peers.get(message.sender_id)
    system_sender = member.conversation.channel == Conversation.Channel.SYSTEM and message.sender_id == member.conversation.created_by_id
    reply = None
    original = message.reply_to if message.reply_to_id else None
    if original and original.conversation_id == member.conversation_id and original.sender_id not in member._payload_blocked and member.joined_at and original.created_at >= member.joined_at and (not member.left_at or original.updated_at <= member.left_at):
        reply = {"id": str(original.pk), "body": "" if original.deleted_at else original.body[:200], "sender_id": original.sender_id, "deleted": bool(original.deleted_at)}
    return {
        "id": str(message.pk), "sender_id": message.sender_id,
        "sender_name": sender.label if sender else ("System" if system_sender else ""), "client_id": str(message.client_id),
        "sequence": message.sequence, "event_sequence": message.event_sequence,
        "body": "" if deleted else message.body, "created_at": message.created_at.isoformat(),
        "location": None if deleted else message.location,
        "edited": bool(message.edited_at), "deleted": deleted, "reply": reply,
        "attachments": [] if deleted else [{"id": str(a.pk), "name": a.name, "kind": a.kind, "mime_type": a.mime_type, "size": a.size, "url": f"/api/chat/attachments/{a.pk}/"} for a in message.attachments.all()],
        "reactions": [] if deleted else [{"user_id": r.user_id, "emoji": r.emoji} for r in message.reactions.all() if r.user_id not in member._payload_blocked],
    }


def conversation_payload(member):
    conv = member.conversation
    blocked = blocked_ids(member.user)
    participants = list(conv.participants.select_related("user"))
    last = visible_messages(member).order_by("-sequence").first()
    writable = can_send(member)
    now = timezone.now()
    receipt_users = set(ChatPreference.objects.filter(user_id__in=[p.user_id for p in participants], read_receipts=True).values_list("user_id", flat=True))
    others = [p for p in participants if p.user_id != member.user_id and p.user_id not in blocked]
    return {
        "id": str(conv.pk), "kind": conv.kind, "channel": conv.channel,
        "title": conv.title if conv.kind == "group" else (others[0].label if others else "Kontakt"),
        "friendship_id": str(conv.friendship_id) if conv.friendship_id else None,
        "family_id": str(conv.family_id) if conv.family_id else None,
        "family_group": conv.channel == Conversation.Channel.FAMILY,
        "system_chat": conv.channel == Conversation.Channel.SYSTEM,
        "state": member.state, "can_send": writable, "muted": member.muted,
        "revision": conv.revision, "last_read_sequence": member.last_read_sequence,
        "unread": visible_messages(member).filter(sequence__gt=member.last_read_sequence).exclude(sender=member.user).count(),
        "last_message": {"id": str(last.pk), "body": "" if last.deleted_at else last.body[:200], "has_location": bool(last.location) and not last.deleted_at, "deleted": bool(last.deleted_at), "created_at": last.created_at.isoformat(), "sender_id": last.sender_id} if last else None,
        "participants": [{"id": p.user_id, "display_name": p.label, "state": p.state, "avatar_url": f"/api/chat/avatars/{p.user_id}/" if p.state == "active" and p.user_id not in blocked else None} for p in participants if p.user_id not in blocked],
        "typing": [{"id": p.user_id, "display_name": p.label} for p in others if writable and p.state == "active" and p.typing_until and p.typing_until > now],
        "read_receipts": [{"user_id": p.user_id, "sequence": p.last_read_sequence} for p in others if writable and p.state == "active" and p.user_id in receipt_users],
    }
