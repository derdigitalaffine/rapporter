from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from mailing.models import TransactionalEmail


INVITATION_DELIVERY_BATCH_SIZE = 200


def invitation_email_rows(invite):
    return TransactionalEmail.objects.filter(
        reference_type="family.invitation",
        reference_id__startswith=f"{invite.pk}:",
    )


def latest_invitation_email(invite):
    return invitation_email_rows(invite).order_by("-created_at").first()


def last_successful_invitation_send(invite):
    return (
        invitation_email_rows(invite)
        .filter(sent_at__isnull=False)
        .order_by("-sent_at")
        .values_list("sent_at", flat=True)
        .first()
    )


def _delivery_status(invite, latest, *, now=None):
    now = now or timezone.now()
    if invite.accepted_at:
        return "accepted"
    if invite.revoked_at:
        return "revoked"
    if invite.expires_at <= now:
        return "expired"
    if latest is None:
        return "preparing"
    if latest.status in {TransactionalEmail.Status.QUEUED, TransactionalEmail.Status.SENDING}:
        return "preparing"
    if latest.status == TransactionalEmail.Status.RETRY:
        return "retrying"
    if latest.status == TransactionalEmail.Status.SENT:
        return "sent"
    if latest.status in {TransactionalEmail.Status.FAILED, TransactionalEmail.Status.CANCELED}:
        return "failed"
    return "preparing"


def prime_invitation_delivery_summaries(invites, *, batch_size=INVITATION_DELIVERY_BATCH_SIZE):
    """Populate invitation delivery caches with bounded batch queries.

    ``TransactionalEmail.reference_id`` includes an invitation UUID plus a nonce,
    so there is no direct FK to prefetch. We group a bounded set of prefix
    predicates into one query per batch and derive both latest status and last
    successful send in memory. Individual callers keep the existing fallback.
    """
    invite_by_id = {str(invite.pk): invite for invite in invites}
    invite_ids = list(invite_by_id)
    if not invite_ids:
        return
    batch_size = max(1, int(batch_size or INVITATION_DELIVERY_BATCH_SIZE))
    now = timezone.now()

    for offset in range(0, len(invite_ids), batch_size):
        chunk_ids = invite_ids[offset : offset + batch_size]
        selector = Q()
        for invite_id in chunk_ids:
            selector |= Q(reference_id__startswith=f"{invite_id}:")
        states = {invite_id: {"latest": None, "last_sent_at": None} for invite_id in chunk_ids}
        rows = (
            TransactionalEmail.objects.filter(reference_type="family.invitation")
            .filter(selector)
            .only("reference_id", "status", "created_at", "sent_at")
            .order_by("-created_at")
        )
        for row in rows:
            invite_id = str(row.reference_id or "").split(":", 1)[0]
            state = states.get(invite_id)
            if state is None:
                continue
            if state["latest"] is None:
                state["latest"] = row
            if row.sent_at is not None and (
                state["last_sent_at"] is None or row.sent_at > state["last_sent_at"]
            ):
                state["last_sent_at"] = row.sent_at

        for invite_id, state in states.items():
            invite = invite_by_id[invite_id]
            invite._invitation_delivery_summary = {
                "delivery_status": _delivery_status(invite, state["latest"], now=now),
                "last_sent_at": state["last_sent_at"],
            }


def invitation_delivery_summary(invite):
    cached = getattr(invite, "_invitation_delivery_summary", None)
    if cached is not None:
        return cached

    latest = latest_invitation_email(invite)
    summary = {
        "delivery_status": _delivery_status(invite, latest),
        "last_sent_at": last_successful_invitation_send(invite),
    }
    invite._invitation_delivery_summary = summary
    return summary
