from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from auth_sessions.service import revoke_all_user_sessions
from mailing.service import enqueue_transactional_email

from .models import EmailIdentity
from .service import primary_identity, verified_user_for_email


class PasswordResetError(ValueError):
    pass


class VersionedPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "familyos.password-reset.v1"

    def _make_hash_value(self, user, timestamp):
        identity = primary_identity(user)
        version = identity.password_reset_version if identity else -1
        return f"{super()._make_hash_value(user, timestamp)}:{version}"


password_reset_token_generator = VersionedPasswordResetTokenGenerator()


@lru_cache(maxsize=1)
def _dummy_password_hash():
    return make_password("familyos-password-reset-timing-budget")


def _consume_timing_budget(value):
    check_password(str(value or ""), _dummy_password_hash())


def _locale(value):
    return "en" if str(value or "").lower().startswith("en") else "de"


def _parse_reference(reference_id):
    try:
        raw_id, raw_version = str(reference_id).split(":", 1)
        return int(raw_id), int(raw_version)
    except (TypeError, ValueError):
        return None, None


def request_password_reset(email, *, locale="de") -> bool:
    """Queue a reset mail for an eligible account without exposing eligibility."""
    # Apply the same password-hash work to every public request so an unknown
    # address does not get a clearly cheaper code path than an eligible one.
    _consume_timing_budget(email)
    user = verified_user_for_email(email)
    if not user:
        return False

    locale = _locale(locale)
    now = timezone.now()
    cooldown = max(0, int(getattr(settings, "PASSWORD_RESET_RESEND_COOLDOWN_SECONDS", 60)))
    with transaction.atomic():
        identity = (
            EmailIdentity.objects.select_for_update()
            .select_related("user")
            .filter(
                user=user,
                kind=EmailIdentity.Kind.PRIMARY,
                verified_at__isnull=False,
            )
            .first()
        )
        if not identity or not identity.user.is_active:
            return False
        if (
            cooldown
            and identity.password_reset_requested_at
            and identity.password_reset_requested_at + timedelta(seconds=cooldown) > now
        ):
            return False

        identity.password_reset_version += 1
        identity.password_reset_requested_at = now
        identity.save(
            update_fields=["password_reset_version", "password_reset_requested_at", "updated_at"]
        )
        enqueue_transactional_email(
            message_key=f"password-reset:{identity.pk}:v{identity.password_reset_version}",
            template_key="password.reset",
            recipient=identity.email,
            locale=locale,
            context={"action_label": "Passwort zurücksetzen" if locale == "de" else "Reset password"},
            reference_type="password_reset",
            reference_id=f"{identity.pk}:{identity.password_reset_version}",
        )
        return True


def password_reset_path(reference_id: str) -> str:
    identity_id, version = _parse_reference(reference_id)
    if identity_id is None:
        return ""
    identity = (
        EmailIdentity.objects.select_related("user")
        .filter(
            pk=identity_id,
            kind=EmailIdentity.Kind.PRIMARY,
            verified_at__isnull=False,
            password_reset_version=version,
            password_reset_requested_at__isnull=False,
        )
        .first()
    )
    if not identity or not identity.user.is_active:
        return ""
    timeout = max(1, int(getattr(settings, "PASSWORD_RESET_TIMEOUT", 3600)))
    if identity.password_reset_requested_at + timedelta(seconds=timeout) < timezone.now():
        return ""
    uid = urlsafe_base64_encode(force_bytes(identity.user_id))
    token = password_reset_token_generator.make_token(identity.user)
    return f"/reset-password/{uid}/{quote(token, safe='')}"


def complete_password_reset(uid, token, new_password, *, locale="de"):
    try:
        user_id = int(force_str(urlsafe_base64_decode(str(uid or ""))))
    except (TypeError, ValueError, UnicodeDecodeError, OverflowError) as exc:
        raise PasswordResetError("Reset-Link ist ungültig oder abgelaufen.") from exc

    locale = _locale(locale)
    with transaction.atomic():
        identity = (
            EmailIdentity.objects.select_for_update()
            .select_related("user")
            .filter(
                user_id=user_id,
                kind=EmailIdentity.Kind.PRIMARY,
                verified_at__isnull=False,
                password_reset_requested_at__isnull=False,
            )
            .first()
        )
        if not identity or not identity.user.is_active:
            raise PasswordResetError("Reset-Link ist ungültig oder abgelaufen.")

        user = identity.user
        if not password_reset_token_generator.check_token(user, str(token or "")):
            raise PasswordResetError("Reset-Link ist ungültig oder abgelaufen.")

        password_validation.validate_password(str(new_password or ""), user=user)
        user.set_password(str(new_password))
        user.save(update_fields=["password"])

        identity.password_reset_version += 1
        identity.password_reset_requested_at = None
        identity.save(
            update_fields=["password_reset_version", "password_reset_requested_at", "updated_at"]
        )
        revoke_all_user_sessions(user, reason="password_reset")

        changed_at = timezone.localtime(timezone.now())
        if locale == "de":
            details = f"Passwort geändert am {changed_at:%d.%m.%Y um %H:%M %Z}. Alle bestehenden Sitzungen wurden aus Sicherheitsgründen beendet."
            support = "Wenn du diese Änderung nicht vorgenommen hast, melde dich an und prüfe deine Sicherheits- und Sitzungsdaten."
        else:
            details = f"Password changed at {changed_at:%Y-%m-%d %H:%M %Z}. All existing sessions were ended for security reasons."
            support = "If you did not make this change, sign in and review your security and session settings."
        enqueue_transactional_email(
            message_key=f"password-changed:{user.pk}:reset-v{identity.password_reset_version}",
            template_key="password.changed",
            recipient=identity.email,
            locale=locale,
            context={"details": details, "support_text": support},
        )
        return user
