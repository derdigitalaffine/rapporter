from django.db import transaction
from django.utils import timezone

from family.models import Family, Membership
from .access import WRITER_ROLES, membership, preferences
from .models import Conversation, ConversationMember


def _active_family_members(family_id):
    return list(
        Membership.objects.filter(
            family_id=family_id,
            family__status="active",
            role__in=WRITER_ROLES,
            user__is_active=True,
        )
        .select_related("user")
        .order_by("created_at", "pk")
    )


@transaction.atomic
def sync_family_conversation(user, family_id):
    own = Membership.objects.filter(
        user=user,
        family_id=family_id,
        family__status="active",
        role__in=WRITER_ROLES,
    ).first()
    if not own:
        return None
    family = Family.objects.select_for_update().get(pk=family_id, status="active")
    conversation, created = Conversation.objects.get_or_create(
        family=family,
        defaults={"kind": "group", "title": family.name, "created_by": user},
    )
    if not created and conversation.title != family.name:
        conversation.title = family.name
        conversation.save(update_fields=["title", "updated_at"])

    desired = {row.user_id: row for row in _active_family_members(family.pk)}
    existing = {
        row.user_id: row
        for row in ConversationMember.objects.select_for_update().filter(conversation=conversation)
    }
    now = timezone.now()

    for user_id, family_member in desired.items():
        label = family_member.display_name or preferences(family_member.user).display_name
        row = existing.get(user_id)
        if row is None:
            ConversationMember.objects.create(
                conversation=conversation,
                user=family_member.user,
                invited_by=user,
                label=label,
                state="active",
                joined_at=now,
            )
            continue
        changed = []
        if row.state != "active":
            row.state = "active"
            row.joined_at = now
            row.left_at = None
            row.typing_until = None
            changed.extend(["state", "joined_at", "left_at", "typing_until"])
        if row.label != label:
            row.label = label
            changed.append("label")
        if changed:
            row.save(update_fields=[*changed, "updated_at"])

    stale_ids = set(existing) - set(desired)
    for user_id in stale_ids:
        row = existing[user_id]
        if row.state == "active":
            row.state = "left"
            row.left_at = now
            row.typing_until = None
            row.save(update_fields=["state", "left_at", "typing_until", "updated_at"])

    return membership(user, conversation.pk)


def sync_family_conversations(user):
    family_ids = list(
        Membership.objects.filter(
            user=user,
            family__status="active",
            role__in=WRITER_ROLES,
        ).values_list("family_id", flat=True)
    )
    return [row for family_id in family_ids if (row := sync_family_conversation(user, family_id))]
