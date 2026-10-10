from __future__ import annotations

import logging
import unicodedata
import uuid
from functools import lru_cache
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from mailing.service import enqueue_transactional_email

from .models import EmailIdentity

logger = logging.getLogger("security.auth_identity")
VERIFY_SALT = "familyos.email-verification.v1"


class EmailIdentityError(ValueError):
    pass


class EmailConflictError(EmailIdentityError):
    pass


class EmailVerificationError(EmailIdentityError):
    pass


def normalize_email(value: object) -> str:
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not raw or "@" not in raw:
        raise EmailIdentityError("Ungültige E-Mail-Adresse.")
    local, domain = raw.rsplit("@", 1)
    normalized = f"{local.casefold()}@{domain.casefold()}"
    try:
        validate_email(normalized)
    except ValidationError as exc:
        raise EmailIdentityError("Ungültige E-Mail-Adresse.") from exc
    return normalized


def primary_identity(user):
    if not user or not getattr(user, "pk", None):
        return None
    return EmailIdentity.objects.filter(user=user, kind=EmailIdentity.Kind.PRIMARY).first()


def pending_identity(user):
    if not user or not getattr(user, "pk", None):
        return None
    return EmailIdentity.objects.filter(user=user, kind=EmailIdentity.Kind.PENDING).first()


def identity_summary(user) -> dict:
    primary = primary_identity(user)
    pending = pending_identity(user)
    return {
        "email": primary.email if primary else "",
        "email_verified": bool(primary and primary.verified_at),
        "email_verified_at": primary.verified_at if primary else None,
        "email_action_required": primary is None,
        "pending_email": pending.email if pending else "",
        "pending_verification_sent_at": pending.verification_sent_at if pending else None,
    }


def _email_conflicts(normalized: str, *, user_id=None) -> bool:
    identities = EmailIdentity.objects.filter(email_normalized=normalized)
    if user_id is not None:
        identities = identities.exclude(user_id=user_id)
    if identities.exists():
        return True
    users = get_user_model().objects.filter(email__iexact=normalized)
    if user_id is not None:
        users = users.exclude(pk=user_id)
    return users.exists()


def create_primary_identity(user, email: str, *, verified=False) -> EmailIdentity:
    normalized = normalize_email(email)
    if _email_conflicts(normalized, user_id=user.pk):
        raise EmailConflictError("Diese E-Mail-Adresse kann nicht verwendet werden.")
    try:
        with transaction.atomic():
            identity = EmailIdentity.objects.create(
                user=user,
                kind=EmailIdentity.Kind.PRIMARY,
                email=normalized,
                email_normalized=normalized,
                verified_at=timezone.now() if verified else None,
            )
            if user.email != normalized:
                user.email = normalized
                user.save(update_fields=["email"])
            return identity
    except IntegrityError as exc:
        raise EmailConflictError("Diese E-Mail-Adresse kann nicht verwendet werden.") from exc


def request_pending_email(user, email: str) -> EmailIdentity:
    normalized = normalize_email(email)
    current = primary_identity(user)
    if current and current.email_normalized == normalized:
        raise EmailConflictError("Diese E-Mail-Adresse ist bereits aktiv.")
    if _email_conflicts(normalized, user_id=user.pk):
        raise EmailConflictError("Diese E-Mail-Adresse kann nicht verwendet werden.")
    try:
        with transaction.atomic():
            EmailIdentity.objects.filter(user=user, kind=EmailIdentity.Kind.PENDING).delete()
            return EmailIdentity.objects.create(
                user=user,
                kind=EmailIdentity.Kind.PENDING,
                email=normalized,
                email_normalized=normalized,
            )
    except IntegrityError as exc:
        raise EmailConflictError("Diese E-Mail-Adresse kann nicht verwendet werden.") from exc


def generate_internal_username() -> str:
    User = get_user_model()
    for _ in range(5):
        username = f"user_{uuid.uuid4().hex[:24]}"
        if not User.objects.filter(username=username).exists():
            return username
    raise RuntimeError("Konnte keinen internen Benutzernamen erzeugen.")


@lru_cache(maxsize=1)
def _dummy_password_hash():
    return make_password("familyos-invalid-login-dummy")


def authenticate_identifier(identifier: str, password: str, *, legacy=False):
    user = None
    if legacy:
        candidate = get_user_model().objects.filter(username__iexact=str(identifier or "").strip()).first()
        if candidate and (
            candidate.is_superuser
            or not EmailIdentity.objects.filter(user=candidate, kind=EmailIdentity.Kind.PRIMARY).exists()
        ):
            user = candidate
    else:
        try:
            normalized = normalize_email(identifier)
        except EmailIdentityError:
            normalized = ""
        if normalized:
            identity = (
                EmailIdentity.objects.select_related("user")
                .filter(kind=EmailIdentity.Kind.PRIMARY, email_normalized=normalized)
                .first()
            )
            user = identity.user if identity else None

    if not user or not user.is_active:
        check_password(password or "", _dummy_password_hash())
        return None
    if not user.check_password(password or ""):
        return None
    return user


def _signer():
    return signing.TimestampSigner(salt=VERIFY_SALT)


def verification_token(identity: EmailIdentity) -> str:
    return _signer().sign_object({"id": identity.pk, "v": identity.verification_version}, compress=True)


def _parse_reference(reference_id: str):
    try:
        raw_id, raw_version = str(reference_id).split(":", 1)
        return int(raw_id), int(raw_version)
    except (TypeError, ValueError):
        return None, None


def verification_path(reference_id: str) -> str:
    identity_id, version = _parse_reference(reference_id)
    if identity_id is None:
        return ""
    identity = EmailIdentity.objects.filter(
        pk=identity_id,
        verification_version=version,
        verified_at__isnull=True,
    ).first()
    if not identity:
        return ""
    token = verification_token(identity)
    return f"/verify-email/{quote(token, safe='')}"


def queue_verification(identity: EmailIdentity, *, locale="de") -> EmailIdentity:
    locale = "en" if str(locale or "").lower().startswith("en") else "de"
    with transaction.atomic():
        locked = EmailIdentity.objects.select_for_update().get(pk=identity.pk)
        if locked.verified_at:
            return locked
        locked.verification_version += 1
        locked.verification_sent_at = timezone.now()
        locked.save(update_fields=["verification_version", "verification_sent_at", "updated_at"])
        enqueue_transactional_email(
            message_key=f"email-verify:{locked.pk}:v{locked.verification_version}",
            template_key="email.verify",
            recipient=locked.email,
            locale=locale,
            context={"action_label": "E-Mail bestätigen" if locale == "de" else "Verify email"},
            reference_type="email_identity.verify",
            reference_id=f"{locked.pk}:{locked.verification_version}",
        )
        return locked


def verify_email_token(token: str) -> tuple[EmailIdentity, bool]:
    try:
        payload = _signer().unsign_object(
            token,
            max_age=int(getattr(settings, "EMAIL_VERIFICATION_MAX_AGE_SECONDS", 86400)),
        )
        identity_id = int(payload["id"])
        version = int(payload["v"])
    except (signing.BadSignature, signing.SignatureExpired, KeyError, TypeError, ValueError) as exc:
        raise EmailVerificationError("Bestätigungslink ist ungültig oder abgelaufen.") from exc

    with transaction.atomic():
        identity = (
            EmailIdentity.objects.select_for_update()
            .select_related("user")
            .filter(pk=identity_id)
            .first()
        )
        if not identity or identity.verification_version != version:
            raise EmailVerificationError("Bestätigungslink ist ungültig oder abgelaufen.")
        if identity.kind == EmailIdentity.Kind.PRIMARY and identity.verified_at:
            return identity, False

        user = identity.user
        now = timezone.now()
        old_email = ""
        if identity.kind == EmailIdentity.Kind.PENDING:
            previous = (
                EmailIdentity.objects.select_for_update()
                .filter(user=user, kind=EmailIdentity.Kind.PRIMARY)
                .first()
            )
            if previous:
                old_email = previous.email if previous.verified_at else ""
                previous.delete()
            identity.kind = EmailIdentity.Kind.PRIMARY

        identity.verified_at = now
        identity.save(update_fields=["kind", "verified_at", "updated_at"])
        if user.email != identity.email:
            user.email = identity.email
            user.save(update_fields=["email"])

        if old_email and old_email != identity.email:
            enqueue_transactional_email(
                message_key=f"email-change:{user.pk}:{identity.pk}:v{identity.verification_version}",
                template_key="email.changed",
                recipient=old_email,
                locale="de",
                context={},
            )
        return identity, True


def verified_user_for_email(email: str):
    try:
        normalized = normalize_email(email)
    except EmailIdentityError:
        return None
    identity = (
        EmailIdentity.objects.select_related("user")
        .filter(
            kind=EmailIdentity.Kind.PRIMARY,
            email_normalized=normalized,
            verified_at__isnull=False,
        )
        .first()
    )
    return identity.user if identity and identity.user.is_active else None
