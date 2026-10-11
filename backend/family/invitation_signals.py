from __future__ import annotations

import uuid

from django.db.models.signals import post_save
from django.dispatch import receiver

from mailing.models import TransactionalEmail

from .invitation_audit import record_invite_audit
from .models import FamilyInvitation


def _invitation_from_mail(row):
    if row.reference_type != "family.invitation":
        return None
    try:
        raw_id, _nonce = str(row.reference_id).split(":", 1)
        invite_id = uuid.UUID(raw_id)
    except (TypeError, ValueError):
        return None
    return FamilyInvitation.objects.select_related("family").filter(pk=invite_id).first()


@receiver(post_save, sender=TransactionalEmail, dispatch_uid="family_invitation_mail_audit")
def audit_invitation_mail(sender, instance, created, update_fields=None, **kwargs):
    invite = _invitation_from_mail(instance)
    if invite is None:
        return

    if created and instance.status == TransactionalEmail.Status.QUEUED:
        record_invite_audit("invite.email_queued", invite)
        return

    if update_fields is not None and "status" not in update_fields:
        return
    if instance.status == TransactionalEmail.Status.SENT:
        record_invite_audit("invite.sent", invite)
    elif instance.status in {TransactionalEmail.Status.FAILED, TransactionalEmail.Status.CANCELED}:
        record_invite_audit(
            "invite.email_failed",
            invite,
            outcome="failed",
            reason="system",
            error_class=instance.last_error_code or "delivery_failed",
        )
