from __future__ import annotations

import hmac
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from auth_identity.models import EmailIdentity
from auth_identity.service import primary_identity, verified_user_for_email
from auth_sessions.service import revoke_all_user_sessions
from mailing.service import enqueue_transactional_email
from telemetry.service import try_record_audit_event

from .models import PasswordResetState

RESET_SALT = "familyos.password-reset.v1"
PASSWORD_STAMP_SALT = "familyos.password-reset.password.v1"


class PasswordResetTokenError(ValueError):
    def __init__(self, reason="unknown"):
        self.reason = reason
        super().__init__("Passwort-Link ist ungültig oder abgelaufen.")


def _locale(value):
    return "en" if str(value or "").lower().startswith("en") else "de"


def _signer():
    return signing.TimestampSigner(salt=RESET_SALT)


def _password_stamp(user):
    return salted_hmac(
        PASSWORD_STAMP_SALT,
        user.password,
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


def password_reset_token(state: PasswordResetState) -> str:
    if not state.identity_id:
        raise PasswordResetTokenError("revoked")
    return _signer().sign_object(
        {
            "id": state.pk,
            "v": state.version,
            "i": state.identity_id,
            "p": _password_stamp(state.user),
        },
        compress=True,
    )


def _parse_reference(reference_id):
    try:
        raw_id, raw_version = str(reference_id).split(":", 1)
        return int(raw_id), int(raw_version)
    except (TypeError, ValueError):
        return None, None


def password_reset_path(reference_id):
    state_id, version = _parse_reference(reference_id)
    if state_id is None:
        return ""
    state = (
        PasswordResetState.objects.select_related("user", "identity")
        .filter(
            pk=state_id,
            version=version,
            consumed_at__isnull=True,
            user__is_active=True,
            identity__kind=EmailIdentity.Kind.PRIMARY,
            identity__verified_at__isnull=False,
        )
        .first()
    )
    if not state or not state.identity_id or state.identity.user_id != state.user_id:
        return ""
    token = password_reset_token(state)
    # Fragments are never sent in HTTP requests, so the reset token does not
    # appear in reverse-proxy/application access-log paths or Referer headers.
    return f"/password-reset#token={quote(token, safe='')}"


def security_center_path(_reference_id):
    return "/?page=profile"


def request_password_reset(email, *, locale="de"):
    user = verified_user_for_email(email)
    if not user:
        return "ineligible"
    identity = primary_identity(user)
    if not identity or not identity.verified_at:
        return "ineligible"

    now = timezone.now()
    cooldown = max(0, int(getattr(settings, "PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS", 60)))
    with transaction.atomic():
        state, _created = PasswordResetState.objects.get_or_create(user=user)
        state = PasswordResetState.objects.select_for_update().get(pk=state.pk)
        if state.requested_at and state.requested_at >= now - timedelta(seconds=cooldown):
            return "cooldown"
        state.identity = identity
        state.version += 1
        state.requested_at = now
        state.consumed_at = None
        state.save(update_fields=["identity", "version", "requested_at", "consumed_at", "updated_at"])
        language = _locale(locale)
        enqueue_transactional_email(
            message_key=f"password-reset:{state.pk}:v{state.version}",
            template_key="password.reset",
            recipient=identity.email,
            locale=language,
            context={
                "action_label": "Passwort zurücksetzen" if language == "de" else "Reset password",
                "support_text": (
                    "Wenn du das nicht angefordert hast, kannst du diese Nachricht ignorieren."
                    if language == "de"
                    else "If you did not request this, you can ignore this message."
                ),
            },
            reference_type="auth_recovery.reset",
            reference_id=f"{state.pk}:{state.version}",
        )
    return "queued"


def _decode_token(token):
    try:
        payload = _signer().unsign_object(
            str(token or ""),
            max_age=max(1, int(getattr(settings, "PASSWORD_RESET_MAX_AGE_SECONDS", 3600))),
        )
    except signing.SignatureExpired as exc:
        raise PasswordResetTokenError("expired") from exc
    except signing.BadSignature as exc:
        raise PasswordResetTokenError("unknown") from exc
    try:
        return {
            "id": int(payload["id"]),
            "v": int(payload["v"]),
            "i": int(payload["i"]),
            "p": str(payload["p"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise PasswordResetTokenError("unknown") from exc


def _validate_state(state, payload):
    if not state or not state.user.is_active:
        raise PasswordResetTokenError("unknown")
    if state.version != payload["v"] or state.consumed_at is not None:
        raise PasswordResetTokenError("revoked")
    identity = state.identity
    if (
        not identity
        or identity.pk != payload["i"]
        or identity.user_id != state.user_id
        or identity.kind != EmailIdentity.Kind.PRIMARY
        or identity.verified_at is None
    ):
        raise PasswordResetTokenError("revoked")
    if not hmac.compare_digest(_password_stamp(state.user), payload["p"]):
        raise PasswordResetTokenError("revoked")
    return state


def validate_password_reset_token(token):
    payload = _decode_token(token)
    state = (
        PasswordResetState.objects.select_related("user", "identity")
        .filter(pk=payload["id"])
        .first()
    )
    return _validate_state(state, payload)


def complete_password_reset(token, new_password):
    payload = _decode_token(token)
    with transaction.atomic():
        state = (
            PasswordResetState.objects.select_for_update()
            .select_related("user", "identity")
            .filter(pk=payload["id"])
            .first()
        )
        state = _validate_state(state, payload)
        user = state.user
        identity = state.identity
        validate_password(new_password, user=user)

        used_version = state.version
        user.set_password(new_password)
        user.save(update_fields=["password"])
        state.version += 1
        state.consumed_at = timezone.now()
        state.save(update_fields=["version", "consumed_at", "updated_at"])
        revoked = revoke_all_user_sessions(user, reason="password_reset")

        enqueue_transactional_email(
            message_key=f"password-changed:{user.pk}:reset-v{used_version}",
            template_key="password.changed",
            recipient=identity.email,
            locale="de",
            context={
                "action_label": "Sicherheit prüfen",
                "support_text": "Wenn du das nicht warst, prüfe bitte sofort deine Konto-Sicherheit.",
            },
            reference_type="auth_recovery.security_center",
            reference_id="profile",
        )

    try_record_audit_event(
        "auth.password_reset.completed",
        actor=user,
        actor_class="user",
        outcome="success",
        target_type="user",
        target_id=str(user.pk),
    )
    return user, revoked
