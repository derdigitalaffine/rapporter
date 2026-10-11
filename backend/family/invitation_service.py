from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from mailing.service import enqueue_transactional_email

from .invitation_audit import record_invite_audit
from .models import Family, FamilyInvitation

TOKEN_DOMAIN = "familyos.family-invitation.v1"
DEFAULT_INVITE_LIFETIME = timedelta(days=7)
ROLE_LABELS = {
    "owner": {"de": "Owner", "en": "Owner"},
    "adult": {"de": "Erwachsene Person", "en": "Adult"},
    "teen": {"de": "Teenager", "en": "Teen"},
    "child": {"de": "Kind", "en": "Child"},
    "guest": {"de": "Gast", "en": "Guest"},
}


def _token_key() -> bytes:
    value = getattr(settings, "INVITATION_TOKEN_HMAC_KEY", "") or settings.SECRET_KEY
    return str(value).encode("utf-8")


def _new_nonce() -> str:
    return secrets.token_urlsafe(18)


def invitation_token(invite_id, nonce: str) -> str:
    invite_uuid = uuid.UUID(str(invite_id))
    nonce = str(nonce or "")
    if not nonce:
        raise ValueError("Invitation nonce is required.")
    message = f"{TOKEN_DOMAIN}:{invite_uuid}:{nonce}".encode("utf-8")
    mac = hmac.new(_token_key(), message, hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")
    return f"{invite_uuid.hex}.{nonce}.{signature}"


def invitation_token_digest(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _looks_like_digest(value: str) -> bool:
    value = str(value or "")
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@receiver(pre_save, sender=FamilyInvitation, dispatch_uid="family_invitation_digest_at_rest")
def ensure_invitation_digest_at_rest(sender, instance, **kwargs):
    """Defense in depth for legacy/direct model writes: the DB column never gets a raw token."""
    if instance.token and not _looks_like_digest(instance.token):
        instance.token = invitation_token_digest(instance.token)


def resolve_invitation(token: str, *, for_update=False):
    digest = invitation_token_digest(token)
    queryset = FamilyInvitation.objects.select_related("family", "invited_by")
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    return queryset.filter(token=digest).first()


def _reference_id(invite: FamilyInvitation, nonce: str) -> str:
    return f"{invite.pk}:{nonce}"


def _inviter_label(invite: FamilyInvitation) -> str:
    inviter = invite.invited_by
    if inviter is None:
        return "FamilyOS"
    full_name = str(inviter.get_full_name() or "").strip()
    return full_name or str(inviter.username or "FamilyOS")


def _invitation_mail_details(invite: FamilyInvitation, locale: str) -> str:
    role = ROLE_LABELS.get(invite.role, {}).get(locale, invite.role)
    expiry = timezone.localtime(invite.expires_at)
    inviter = _inviter_label(invite)
    if locale == "en":
        expires = expiry.strftime("%Y-%m-%d %H:%M %Z")
        return f"Family: {invite.family.name} · Invited by: {inviter} · Role: {role} · Expires: {expires}"
    expires = expiry.strftime("%d.%m.%Y %H:%M %Z")
    return f"Familie: {invite.family.name} · Eingeladen von: {inviter} · Rolle: {role} · Gültig bis: {expires}"


def queue_invitation_email(invite: FamilyInvitation, nonce: str):
    if not invite.email:
        return None
    token = invitation_token(invite.pk, nonce)
    if not hmac.compare_digest(invite.token, invitation_token_digest(token)):
        raise ValueError("Invitation token generation does not match persisted digest.")
    locale = "en" if str(invite.family.locale or "").lower().startswith("en") else "de"
    return enqueue_transactional_email(
        message_key=f"family-invitation:{invite.pk}:{invite.token[:16]}",
        template_key="family.invitation",
        recipient=invite.email,
        locale=locale,
        context={
            "action_label": "Accept invitation" if locale == "en" else "Einladung annehmen",
            "details": _invitation_mail_details(invite, locale),
        },
        reference_type="family.invitation",
        reference_id=_reference_id(invite, nonce),
    )


def _active_matching_invites(*, family, role, email, now):
    return (
        FamilyInvitation.objects.select_for_update(of=("self",))
        .filter(
            family=family,
            role=role,
            email__iexact=str(email or "").strip(),
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
        )
        .order_by("-created_at", "-id")
    )


def issue_invitation(*, family, invited_by, role, email="", display_name="", expires_at=None):
    email = str(email or "").strip()
    now = timezone.now()
    expiry = expires_at or (now + DEFAULT_INVITE_LIFETIME)
    nonce = _new_nonce()

    with transaction.atomic():
        # Serialize issuance per family so concurrent requests cannot leave multiple
        # active bearer secrets for the same family/email/role tuple.
        Family.objects.select_for_update().get(pk=family.pk)
        matches = list(_active_matching_invites(family=family, role=role, email=email, now=now))
        if matches:
            invite = matches[0]
            for duplicate in matches[1:]:
                duplicate.revoked_at = now
                duplicate.save(update_fields=["revoked_at", "updated_at"])
                record_invite_audit("invite.revoked", duplicate)

            token = invitation_token(invite.pk, nonce)
            invite.invited_by = invited_by
            invite.email = email
            invite.display_name = display_name
            invite.expires_at = expiry
            invite.revoked_at = None
            invite.token = invitation_token_digest(token)
            invite.save(
                update_fields=[
                    "invited_by",
                    "email",
                    "display_name",
                    "expires_at",
                    "revoked_at",
                    "token",
                    "updated_at",
                ]
            )
            queue_invitation_email(invite, nonce)
            record_invite_audit("invite.resent", invite, actor=invited_by)
            return invite, token

        invite_id = uuid.uuid4()
        token = invitation_token(invite_id, nonce)
        invite = FamilyInvitation.objects.create(
            id=invite_id,
            family=family,
            invited_by=invited_by,
            role=role,
            email=email,
            display_name=display_name,
            expires_at=expiry,
            token=invitation_token_digest(token),
        )
        queue_invitation_email(invite, nonce)
        record_invite_audit("invite.created", invite, actor=invited_by)
    return invite, token


def rotate_invitation(invite: FamilyInvitation, *, expires_at=None, actor=None):
    nonce = _new_nonce()
    with transaction.atomic():
        locked = (
            FamilyInvitation.objects.select_for_update(of=("self",))
            .select_related("family", "invited_by")
            .get(pk=invite.pk)
        )
        if locked.accepted_at:
            raise ValueError("Angenommene Einladung kann nicht erneuert werden.")
        token = invitation_token(locked.pk, nonce)
        locked.token = invitation_token_digest(token)
        locked.revoked_at = None
        locked.expires_at = expires_at or (timezone.now() + DEFAULT_INVITE_LIFETIME)
        locked.save(update_fields=["token", "revoked_at", "expires_at", "updated_at"])
        queue_invitation_email(locked, nonce)
        record_invite_audit("invite.resent", locked, actor=actor or locked.invited_by)
    return locked, token


def invitation_path(reference_id: str) -> str:
    try:
        raw_id, nonce = str(reference_id).split(":", 1)
        invite_id = uuid.UUID(raw_id)
    except (TypeError, ValueError):
        return ""
    invite = FamilyInvitation.objects.filter(pk=invite_id).first()
    if not invite or not invite.is_active:
        return ""
    token = invitation_token(invite.pk, nonce)
    if not hmac.compare_digest(invite.token, invitation_token_digest(token)):
        return ""
    return f"/invite/{quote(token, safe='')}"
