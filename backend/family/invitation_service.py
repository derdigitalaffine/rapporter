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

from .models import FamilyInvitation

TOKEN_DOMAIN = "familyos.family-invitation.v1"
DEFAULT_INVITE_LIFETIME = timedelta(days=7)


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
        queryset = queryset.select_for_update()
    return queryset.filter(token=digest).first()


def _reference_id(invite: FamilyInvitation, nonce: str) -> str:
    return f"{invite.pk}:{nonce}"


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
            "details": f"Family: {invite.family.name}" if locale == "en" else f"Familie: {invite.family.name}",
        },
        reference_type="family.invitation",
        reference_id=_reference_id(invite, nonce),
    )


def issue_invitation(*, family, invited_by, role, email="", display_name="", expires_at=None):
    invite_id = uuid.uuid4()
    nonce = _new_nonce()
    token = invitation_token(invite_id, nonce)
    with transaction.atomic():
        invite = FamilyInvitation.objects.create(
            id=invite_id,
            family=family,
            invited_by=invited_by,
            role=role,
            email=email,
            display_name=display_name,
            expires_at=expires_at or (timezone.now() + DEFAULT_INVITE_LIFETIME),
            token=invitation_token_digest(token),
        )
        queue_invitation_email(invite, nonce)
    return invite, token


def rotate_invitation(invite: FamilyInvitation, *, expires_at=None):
    nonce = _new_nonce()
    with transaction.atomic():
        locked = (
            FamilyInvitation.objects.select_for_update()
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
