from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from auth_identity.service import identity_summary
from auth_sessions.models import AuthSession
from auth_sessions.service import create_session, mark_reauthenticated

from .models import WebAuthnChallenge, WebAuthnCredential


class PasskeyUnavailable(APIException):
    status_code = 503
    default_detail = "Passkeys sind für diese Installation nicht konfiguriert."
    default_code = "passkeys_unavailable"


class PasskeyCeremonyError(APIException):
    status_code = 400
    default_detail = "Passkey-Vorgang konnte nicht bestätigt werden."
    default_code = "passkey_ceremony_invalid"


@dataclass(frozen=True)
class PasskeyConfig:
    rp_id: str
    rp_name: str
    origin: str
    challenge_ttl_seconds: int


def passkey_config() -> PasskeyConfig:
    if not getattr(settings, "WEBAUTHN_ENABLED", False):
        raise PasskeyUnavailable()
    origin = (getattr(settings, "WEBAUTHN_ORIGIN", "") or getattr(settings, "APP_URL", "")).strip().rstrip("/")
    parsed = urlparse(origin)
    host = (parsed.hostname or "").lower()
    rp_id = (getattr(settings, "WEBAUTHN_RP_ID", "") or host).strip().lower().strip(".")
    if (
        not origin
        or parsed.scheme not in {"https", "http"}
        or not host
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or "*" in rp_id
        or (host != rp_id and not host.endswith("." + rp_id))
        or (parsed.scheme != "https" and host not in {"localhost", "127.0.0.1", "::1"})
    ):
        raise PasskeyUnavailable()
    return PasskeyConfig(
        rp_id=rp_id,
        rp_name=(getattr(settings, "WEBAUTHN_RP_NAME", "") or "FamilyOS").strip()[:120],
        origin=origin,
        challenge_ttl_seconds=max(60, int(getattr(settings, "WEBAUTHN_CHALLENGE_TTL_SECONDS", 300))),
    )


def _options_payload(options, challenge_record: WebAuthnChallenge) -> dict:
    return {
        "challenge_id": str(challenge_record.pk),
        "options": json.loads(options_to_json(options)),
        "expires_at": challenge_record.expires_at,
    }


def _new_challenge(*, ceremony: str, user=None) -> WebAuthnChallenge:
    cfg = passkey_config()
    now = timezone.now()
    return WebAuthnChallenge.objects.create(
        user=user,
        ceremony=ceremony,
        challenge=os.urandom(32),
        expires_at=now + timedelta(seconds=cfg.challenge_ttl_seconds),
    )


def _consume_challenge(challenge_id, *, ceremony: str, user=None) -> WebAuthnChallenge:
    now = timezone.now()
    with transaction.atomic():
        challenge = (
            WebAuthnChallenge.objects.select_for_update()
            .filter(pk=challenge_id, ceremony=ceremony)
            .first()
        )
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.expires_at <= now
            or (user is not None and challenge.user_id != user.pk)
            or (user is None and challenge.user_id is not None)
        ):
            raise PasskeyCeremonyError()
        challenge.consumed_at = now
        challenge.save(update_fields=["consumed_at"])
    return challenge


def _active_credentials(user):
    return WebAuthnCredential.objects.filter(user=user, revoked_at__isnull=True)


def registration_options(user) -> dict:
    cfg = passkey_config()
    challenge = _new_challenge(ceremony=WebAuthnChallenge.Ceremony.REGISTER, user=user)
    identity = identity_summary(user)
    descriptors = [
        PublicKeyCredentialDescriptor(id=bytes(value))
        for value in _active_credentials(user).values_list("credential_id", flat=True)
    ]
    options = generate_registration_options(
        rp_id=cfg.rp_id,
        rp_name=cfg.rp_name,
        user_id=str(user.pk).encode("utf-8"),
        user_name=identity["email"] or user.username,
        user_display_name=user.get_full_name() or user.username,
        challenge=bytes(challenge.challenge),
        exclude_credentials=descriptors,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    return _options_payload(options, challenge)


def complete_registration(user, *, challenge_id, credential: dict, name: str) -> WebAuthnCredential:
    cfg = passkey_config()
    challenge = _consume_challenge(
        challenge_id,
        ceremony=WebAuthnChallenge.Ceremony.REGISTER,
        user=user,
    )
    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=bytes(challenge.challenge),
            expected_rp_id=cfg.rp_id,
            expected_origin=cfg.origin,
            require_user_verification=True,
        )
    except Exception as exc:
        raise PasskeyCeremonyError() from exc

    transports = credential.get("response", {}).get("transports", [])
    safe_transports = [
        value for value in transports
        if isinstance(value, str) and value in {"usb", "nfc", "ble", "internal", "hybrid", "smart-card"}
    ][:8]
    device_type = getattr(verification, "credential_device_type", "")
    if hasattr(device_type, "value"):
        device_type = device_type.value
    display_name = (name or "Passkey").strip()[:120] or "Passkey"
    try:
        with transaction.atomic():
            return WebAuthnCredential.objects.create(
                user=user,
                credential_id=verification.credential_id,
                public_key=verification.credential_public_key,
                sign_count=max(0, int(verification.sign_count)),
                name=display_name,
                transports=safe_transports,
                device_type=str(device_type or "")[:32],
                backed_up=bool(getattr(verification, "credential_backed_up", False)),
            )
    except IntegrityError as exc:
        raise PasskeyCeremonyError() from exc


def authentication_options(*, user=None, ceremony=WebAuthnChallenge.Ceremony.AUTHENTICATE) -> dict:
    cfg = passkey_config()
    challenge = _new_challenge(ceremony=ceremony, user=user)
    allow_credentials = None
    if user is not None:
        allow_credentials = [
            PublicKeyCredentialDescriptor(id=bytes(value))
            for value in _active_credentials(user).values_list("credential_id", flat=True)
        ]
    option_kwargs = {
        "rp_id": cfg.rp_id,
        "challenge": bytes(challenge.challenge),
        "user_verification": UserVerificationRequirement.REQUIRED,
    }
    if allow_credentials is not None:
        option_kwargs["allow_credentials"] = allow_credentials
    options = generate_authentication_options(**option_kwargs)
    return _options_payload(options, challenge)


def _credential_id_from_response(credential: dict) -> bytes:
    encoded = credential.get("id") or credential.get("rawId")
    if not isinstance(encoded, str) or not encoded:
        raise PasskeyCeremonyError()
    try:
        return base64url_to_bytes(encoded)
    except Exception as exc:
        raise PasskeyCeremonyError() from exc


def _verify_authentication(*, challenge, credential_payload: dict, expected_user=None) -> WebAuthnCredential:
    cfg = passkey_config()
    credential_id = _credential_id_from_response(credential_payload)
    query = WebAuthnCredential.objects.select_related("user").filter(
        credential_id=credential_id,
        revoked_at__isnull=True,
        user__is_active=True,
    )
    if expected_user is not None:
        query = query.filter(user=expected_user)
    stored = query.first()
    if stored is None:
        raise PasskeyCeremonyError()

    try:
        verification = verify_authentication_response(
            credential=credential_payload,
            expected_challenge=bytes(challenge.challenge),
            expected_rp_id=cfg.rp_id,
            expected_origin=cfg.origin,
            credential_public_key=bytes(stored.public_key),
            credential_current_sign_count=int(stored.sign_count),
            require_user_verification=True,
        )
    except Exception as exc:
        raise PasskeyCeremonyError() from exc

    device_type = getattr(verification, "credential_device_type", "")
    if hasattr(device_type, "value"):
        device_type = device_type.value
    stored.sign_count = max(0, int(verification.new_sign_count))
    stored.device_type = str(device_type or stored.device_type)[:32]
    stored.backed_up = bool(getattr(verification, "credential_backed_up", stored.backed_up))
    stored.last_used_at = timezone.now()
    stored.save(update_fields=["sign_count", "device_type", "backed_up", "last_used_at"])
    return stored


def complete_authentication(request, *, challenge_id, credential: dict):
    challenge = _consume_challenge(
        challenge_id,
        ceremony=WebAuthnChallenge.Ceremony.AUTHENTICATE,
        user=None,
    )
    stored = _verify_authentication(challenge=challenge, credential_payload=credential)
    session, access, refresh = create_session(
        stored.user,
        request,
        auth_method=AuthSession.AuthMethod.PASSKEY,
    )
    return stored, session, access, refresh


def complete_reauthentication(request, *, challenge_id, credential: dict) -> WebAuthnCredential:
    challenge = _consume_challenge(
        challenge_id,
        ceremony=WebAuthnChallenge.Ceremony.REAUTHENTICATE,
        user=request.user,
    )
    stored = _verify_authentication(
        challenge=challenge,
        credential_payload=credential,
        expected_user=request.user,
    )
    session = getattr(request, "auth_session", None)
    if session is None:
        raise PasskeyCeremonyError()
    mark_reauthenticated(session, auth_method=AuthSession.AuthMethod.PASSKEY)
    return stored


def serialize_credential(credential: WebAuthnCredential) -> dict:
    return {
        "id": str(credential.pk),
        "name": credential.name,
        "transports": credential.transports,
        "device_type": credential.device_type,
        "backed_up": credential.backed_up,
        "created_at": credential.created_at,
        "last_used_at": credential.last_used_at,
    }


def rename_credential(user, credential_id, *, name: str) -> WebAuthnCredential:
    display_name = str(name or "").strip()
    if not display_name:
        raise PasskeyCeremonyError("Passkey-Name darf nicht leer sein.")
    credential = _active_credentials(user).filter(pk=credential_id).first()
    if credential is None:
        raise PasskeyCeremonyError()
    credential.name = display_name[:120]
    credential.save(update_fields=["name"])
    return credential


def revoke_credential(user, credential_id) -> None:
    with transaction.atomic():
        credential = (
            WebAuthnCredential.objects.select_for_update()
            .filter(pk=credential_id, user=user, revoked_at__isnull=True)
            .first()
        )
        if credential is None:
            raise PasskeyCeremonyError()
        active_count = WebAuthnCredential.objects.filter(user=user, revoked_at__isnull=True).count()
        if active_count <= 1 and not user.has_usable_password():
            raise PasskeyCeremonyError("Der letzte Anmeldeweg kann nicht entfernt werden.")
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["revoked_at"])


def prune_challenges(*, now=None) -> int:
    now = now or timezone.now()
    cutoff = now - timedelta(days=1)
    deleted, _ = WebAuthnChallenge.objects.filter(expires_at__lt=cutoff).delete()
    return deleted
