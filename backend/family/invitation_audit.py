from __future__ import annotations

from django.utils import timezone

from telemetry.models import AuditEvent
from telemetry.service import try_record_audit_event

ROLE_EVENTS = {
    "invite.created",
    "invite.email_queued",
    "invite.sent",
    "invite.email_failed",
    "invite.resent",
    "invite.accepted",
}


def _actor_class(actor):
    if actor is None:
        return "system"
    return "superadmin" if getattr(actor, "is_superuser", False) else "user"


def record_invite_audit(event_key, invite, *, actor=None, outcome="success", reason="", error_class=""):
    metadata = {}
    if event_key in ROLE_EVENTS:
        metadata["role"] = invite.role
    if event_key == "invite.email_failed" and error_class:
        metadata["error_class"] = str(error_class).lower().replace(" ", "_")[:64]
    return try_record_audit_event(
        event_key,
        actor=actor,
        actor_class=_actor_class(actor),
        family=invite.family,
        outcome=outcome,
        reason=reason,
        target_type="invite",
        target_id=str(invite.pk),
        metadata=metadata,
    )


def record_invite_expired_once(invite):
    if invite.accepted_at or invite.revoked_at or invite.expires_at > timezone.now():
        return None
    exists = AuditEvent.objects.filter(
        event_key="invite.expired",
        target_type="invite",
        target_id=str(invite.pk),
    ).exists()
    if exists:
        return None
    return record_invite_audit("invite.expired", invite)
