from __future__ import annotations

from django.utils import timezone

from mailing.models import TransactionalEmail


def latest_invitation_email(invite):
    return (
        TransactionalEmail.objects.filter(
            reference_type="family.invitation",
            reference_id__startswith=f"{invite.pk}:",
        )
        .order_by("-created_at")
        .first()
    )


def invitation_delivery_summary(invite):
    cached = getattr(invite, "_invitation_delivery_summary", None)
    if cached is not None:
        return cached

    latest = latest_invitation_email(invite)
    if invite.accepted_at:
        status = "accepted"
    elif invite.revoked_at:
        status = "revoked"
    elif invite.expires_at <= timezone.now():
        status = "expired"
    elif latest is None:
        status = "preparing"
    elif latest.status in {TransactionalEmail.Status.QUEUED, TransactionalEmail.Status.SENDING}:
        status = "preparing"
    elif latest.status == TransactionalEmail.Status.RETRY:
        status = "retrying"
    elif latest.status == TransactionalEmail.Status.SENT:
        status = "sent"
    elif latest.status in {TransactionalEmail.Status.FAILED, TransactionalEmail.Status.CANCELED}:
        status = "failed"
    else:
        status = "preparing"

    summary = {
        "delivery_status": status,
        "last_sent_at": latest.sent_at if latest else None,
    }
    invite._invitation_delivery_summary = summary
    return summary
