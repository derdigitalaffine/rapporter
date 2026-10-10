from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from mailing.service import enqueue_transactional_email

from .models import FamilyInvitation

TOKEN_DOMAIN = "familyos.family-invitation.v1"
DEFAULT_INVITE_LIFETIME = timedelta(days=7)


def _token_key() -> bytes:
    value = getattr(settings, "INVITATION_TOKEN_HMAC_KEY", "") or settings.SECRET_KEY
    return str(value).encode("utf-8")


def invitation_token(invite_id, version: int) -> str:
    invite_uuid = uuid.UUID(str(invite_id))
    version = int(version)
    if version < 1:
        raise ValueError("Legacy invitation tokens cannot be reconstructed.")
    message = f"{TOKEN_DOMAIN}:{invite_uuid}:{version}".encode("utf-8")
    mac = hmac.new(_token_key(), message, hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")
    return f"{invite_uuid.hex}.{version}.{signature}"


def invitation_token_digest(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def resolve_invitation(token: str, *, for_update=False):
    digest = invitation_token_digest(token)
    queryset = FamilyInvitation.objects.select_related("family", "invited_by")
    if for_update:
        queryset = queryset.select_for_update()
    return queryset.filter(token_digest=digest).first()


def _reference_id(invite: FamilyInvitation) -> str:
    return f"{invite.pk}:{invite.token_version}"


def queue_invitation_email(invite: FamilyInvitation):
    if not invite.email or invite.token_version < 1:
        return None
    locale = "en" if str(invite.family.locale or "").lower().startswith("en") else "de"
    action_label = "Accept invitation" if locale == "en" else "Einladung annehmen"
    details = (
        f"Family: {invite.family.name}"
        if locale == "en"
        else f"Familie: {invite.family.name}"
    )
    return enqueue_transactional_email(
        message_key=f"family-invitation:{invite.pk}:v{invite.token_version}",
        template_key="family.invitation",
        recipient=invite.email,
        locale=locale,
        context={"action_label": action_label, "details": details},
        reference_type="family.invitation",
        reference_id=_reference_id(invite),
    )


def issue_invitation(*, family, invited_by, role, email="", display_name="", expires_at=None):
    invite_id = uuid.uuid4()
    version = 1
    token = invitation_token(invite_id, version)
    with transaction.atomic():
        invite = FamilyInvitation.objects.create(
            id=invite_id,
            family=family,
            invited_by=invited_by,
            role=role,
            email=email,
            display_name=display_name,
            expires_at=expires_at or (timezone.now() + DEFAULT_INVITE_LIFETIME),
            token_digest=invitation_token_digest(token),
            token_version=version,
        )
        queue_invitation_email(invite)
    return invite, token


def rotate_invitation(invite: FamilyInvitation, *, expires_at=None):
    with transaction.atomic():
        locked = (
            FamilyInvitation.objects.select_for_update()
            .select_related("family", "invited_by")
            .get(pk=invite.pk)
        )
        if locked.accepted_at:
            raise ValueError("Angenommene Einladung kann nicht erneuert werden.")
        locked.token_version = max(1, int(locked.token_version or 0) + 1)
        token = invitation_token(locked.pk, locked.token_version)
        locked.token_digest = invitation_token_digest(token)
        locked.revoked_at = None
        locked.expires_at = expires_at or (timezone.now() + DEFAULT_INVITE_LIFETIME)
        locked.save(
            update_fields=[
                "token_version",
                "token_digest",
                "revoked_at",
                "expires_at",
                "updated_at",
            ]
        )
        queue_invitation_email(locked)
    return locked, token


def invitation_path(reference_id: str) -> str:
    try:
        raw_id, raw_version = str(reference_id).split(":", 1)
        invite_id = uuid.UUID(raw_id)
        version = int(raw_version)
    except (TypeError, ValueError):
        return ""
    if version < 1:
        return ""
    invite = FamilyInvitation.objects.filter(pk=invite_id, token_version=version).first()
    if not invite or not invite.is_active:
        return ""
    try:
        token = invitation_token(invite.pk, version)
    except ValueError:
        return ""
    if not hmac.compare_digest(invite.token_digest, invitation_token_digest(token)):
        return ""
    return f"/invite/{quote(token, safe='')}"
