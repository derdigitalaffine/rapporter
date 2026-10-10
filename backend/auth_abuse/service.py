from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import math
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Iterable

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import AuthAbuseBucket

logger = logging.getLogger("security.auth_abuse")


@dataclass(frozen=True)
class WindowPolicy:
    limit: int
    seconds: int


@dataclass(frozen=True)
class KeyPolicy:
    kind: str
    multiplier: int = 1


@dataclass(frozen=True)
class AbusePolicy:
    scope: str
    burst: WindowPolicy
    sustained: WindowPolicy
    keys: tuple[KeyPolicy, ...]
    base_cooldown_seconds: int
    max_cooldown_seconds: int
    audit_category: str


@dataclass(frozen=True)
class AbuseDecision:
    allowed: bool
    scope: str
    retry_after: int = 0
    blocked_by: str = ""


@dataclass(frozen=True)
class IdentityKey:
    kind: str
    digest: str
    multiplier: int


LOGIN_KEYS = (
    KeyPolicy("network", 4),
    KeyPolicy("identifier", 1),
    KeyPolicy("network_identifier", 1),
    KeyPolicy("global", 50),
)
PUBLIC_IDENTIFIER_KEYS = (
    KeyPolicy("network", 4),
    KeyPolicy("identifier", 1),
    KeyPolicy("network_identifier", 1),
    KeyPolicy("global", 50),
)
AUTHENTICATED_KEYS = (
    KeyPolicy("user", 1),
    KeyPolicy("network", 4),
    KeyPolicy("global", 50),
)
INVITE_KEYS = (
    KeyPolicy("user", 1),
    KeyPolicy("family", 2),
    KeyPolicy("network", 4),
    KeyPolicy("global", 50),
)

# Stable scope names are part of the API contract. Future auth work (#201/#202)
# should reuse these entries instead of adding local throttles.
POLICIES: dict[str, AbusePolicy] = {
    "login.password": AbusePolicy(
        "login.password", WindowPolicy(5, 60), WindowPolicy(20, 3600), LOGIN_KEYS, 30, 900, "auth.login.password"
    ),
    "login.passkey.options": AbusePolicy(
        "login.passkey.options", WindowPolicy(10, 60), WindowPolicy(50, 3600), PUBLIC_IDENTIFIER_KEYS, 15, 300, "auth.login.passkey"
    ),
    "login.passkey.verify": AbusePolicy(
        "login.passkey.verify", WindowPolicy(8, 60), WindowPolicy(30, 3600), PUBLIC_IDENTIFIER_KEYS, 30, 900, "auth.login.passkey"
    ),
    "reauth.password": AbusePolicy(
        "reauth.password", WindowPolicy(5, 60), WindowPolicy(15, 3600), AUTHENTICATED_KEYS, 30, 900, "auth.reauth.password"
    ),
    "password_reset.request": AbusePolicy(
        "password_reset.request", WindowPolicy(3, 300), WindowPolicy(8, 3600), PUBLIC_IDENTIFIER_KEYS, 60, 1800, "auth.password_reset"
    ),
    "email_verification.resend": AbusePolicy(
        "email_verification.resend", WindowPolicy(2, 300), WindowPolicy(6, 3600), PUBLIC_IDENTIFIER_KEYS, 60, 1800, "auth.email_verification"
    ),
    "invite.create": AbusePolicy(
        "invite.create", WindowPolicy(5, 60), WindowPolicy(30, 3600), INVITE_KEYS, 30, 900, "auth.invite.create"
    ),
    "invite.resend": AbusePolicy(
        "invite.resend", WindowPolicy(3, 300), WindowPolicy(10, 3600), INVITE_KEYS, 60, 1800, "auth.invite.resend"
    ),
    "webauthn.registration.options": AbusePolicy(
        "webauthn.registration.options", WindowPolicy(10, 60), WindowPolicy(40, 3600), AUTHENTICATED_KEYS, 15, 300, "auth.webauthn.registration"
    ),
    "webauthn.authentication.options": AbusePolicy(
        "webauthn.authentication.options", WindowPolicy(10, 60), WindowPolicy(50, 3600), PUBLIC_IDENTIFIER_KEYS, 15, 300, "auth.webauthn.authentication"
    ),
    "superadmin.sensitive_action": AbusePolicy(
        "superadmin.sensitive_action", WindowPolicy(5, 60), WindowPolicy(20, 3600), AUTHENTICATED_KEYS, 30, 900, "auth.superadmin"
    ),
}


def get_policy(scope: str) -> AbusePolicy:
    try:
        return POLICIES[scope]
    except KeyError as exc:
        raise ValueError(f"Unknown auth abuse scope: {scope}") from exc


def normalize_identifier(value: object) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def _hmac_secret() -> bytes:
    value = getattr(settings, "AUTH_ABUSE_HMAC_KEY", None) or settings.SECRET_KEY
    return str(value).encode("utf-8")


def hash_identity(kind: str, value: object) -> str:
    normalized = normalize_identifier(value)
    payload = f"{kind}:{normalized}".encode("utf-8")
    return hmac.new(_hmac_secret(), payload, hashlib.sha256).hexdigest()


@lru_cache(maxsize=16)
def _parse_trusted_proxy_cidrs(raw: tuple[str, ...]) -> tuple[ipaddress._BaseNetwork, ...]:
    networks = []
    for value in raw:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            logger.error("auth_abuse_invalid_trusted_proxy_cidr cidr=%r", value)
    return tuple(networks)


def _trusted_proxy_networks() -> tuple[ipaddress._BaseNetwork, ...]:
    values = getattr(settings, "AUTH_TRUSTED_PROXY_CIDRS", ()) or ()
    if isinstance(values, str):
        values = tuple(part.strip() for part in values.split(",") if part.strip())
    return _parse_trusted_proxy_cidrs(tuple(values))


def _parse_ip(value: object):
    try:
        return ipaddress.ip_address(str(value).strip())
    except (TypeError, ValueError):
        return None


def client_ip(request):
    if request is None:
        return None
    remote = _parse_ip(request.META.get("REMOTE_ADDR"))
    if remote is None:
        return None

    trusted = _trusted_proxy_networks()
    if not trusted or not any(remote in network for network in trusted):
        return remote

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    chain = [_parse_ip(part) for part in forwarded.split(",") if part.strip()]
    if any(value is None for value in chain):
        return remote

    # Walk right-to-left and discard only explicitly trusted proxy hops. This
    # rejects a client-supplied leftmost XFF value when an untrusted hop exists.
    for candidate in reversed([*chain, remote]):
        if any(candidate in network for network in trusted):
            continue
        return candidate
    return remote


def network_identity(request) -> str:
    address = client_ip(request)
    if address is None:
        return "unknown"
    if address.version == 6:
        prefix = int(getattr(settings, "AUTH_ABUSE_IPV6_PREFIX", 64))
    else:
        prefix = int(getattr(settings, "AUTH_ABUSE_IPV4_PREFIX", 32))
    max_prefix = address.max_prefixlen
    prefix = min(max(prefix, 0), max_prefix)
    return str(ipaddress.ip_network(f"{address}/{prefix}", strict=False))


def _identity_values(*, request=None, identifier=None, user=None, family_id=None) -> dict[str, str]:
    network = network_identity(request)
    normalized_identifier = normalize_identifier(identifier)
    user_id = getattr(user, "pk", None) if user is not None else None
    if user_id is None and request is not None:
        request_user = getattr(request, "user", None)
        if request_user is not None and getattr(request_user, "is_authenticated", False):
            user_id = getattr(request_user, "pk", None)

    values = {
        "network": network,
        "identifier": normalized_identifier,
        "user": str(user_id) if user_id is not None else "",
        "family": str(family_id) if family_id else "",
        "global": "instance",
    }
    if network and normalized_identifier:
        values["network_identifier"] = f"{network}|{normalized_identifier}"
    else:
        values["network_identifier"] = ""
    return values


def build_identity_keys(policy: AbusePolicy, *, request=None, identifier=None, user=None, family_id=None) -> tuple[IdentityKey, ...]:
    values = _identity_values(request=request, identifier=identifier, user=user, family_id=family_id)
    keys = []
    for key_policy in policy.keys:
        value = values.get(key_policy.kind, "")
        if not value:
            continue
        keys.append(
            IdentityKey(
                kind=key_policy.kind,
                digest=hash_identity(key_policy.kind, value),
                multiplier=max(1, int(key_policy.multiplier)),
            )
        )
    return tuple(keys)


def _lock_or_create_bucket(*, scope: str, identity: IdentityKey, window_kind: str, window: WindowPolicy, now):
    lookup = {
        "scope": scope,
        "key_hash": identity.digest,
        "window_kind": window_kind,
    }
    try:
        return AuthAbuseBucket.objects.select_for_update().get(**lookup)
    except AuthAbuseBucket.DoesNotExist:
        try:
            # Keep the unique-race savepoint separate: another worker may have
            # inserted the bucket after our initial SELECT.
            with transaction.atomic():
                AuthAbuseBucket.objects.create(
                    **lookup,
                    key_kind=identity.kind,
                    window_seconds=window.seconds,
                    window_started_at=now,
                    expires_at=now + timedelta(seconds=window.seconds),
                )
        except IntegrityError:
            pass
        return AuthAbuseBucket.objects.select_for_update().get(**lookup)


def _consume_bucket(*, policy: AbusePolicy, identity: IdentityKey, window_kind: str, window: WindowPolicy, now) -> int:
    bucket = _lock_or_create_bucket(
        scope=policy.scope,
        identity=identity,
        window_kind=window_kind,
        window=window,
        now=now,
    )
    effective_limit = max(1, int(window.limit) * identity.multiplier)

    if bucket.window_seconds != window.seconds or bucket.expires_at <= now:
        bucket.window_seconds = window.seconds
        bucket.window_started_at = now
        bucket.expires_at = now + timedelta(seconds=window.seconds)
        bucket.count = 0
        bucket.penalty_level = max(0, bucket.penalty_level - 1)
        bucket.blocked_until = None

    if bucket.blocked_until and bucket.blocked_until > now:
        return max(1, math.ceil((bucket.blocked_until - now).total_seconds()))

    if bucket.blocked_until and bucket.blocked_until <= now:
        # Permit one probe after a cooldown while retaining sustained-window
        # pressure. A successful authentication can explicitly forgive the key.
        bucket.blocked_until = None
        bucket.count = min(bucket.count, max(0, effective_limit - 1))

    if bucket.count >= effective_limit:
        bucket.penalty_level += 1
        cooldown = min(
            policy.max_cooldown_seconds,
            policy.base_cooldown_seconds * (2 ** max(0, bucket.penalty_level - 1)),
        )
        bucket.blocked_until = now + timedelta(seconds=cooldown)
        if bucket.expires_at < bucket.blocked_until:
            bucket.expires_at = bucket.blocked_until
        bucket.save(
            update_fields=[
                "window_seconds",
                "window_started_at",
                "expires_at",
                "count",
                "penalty_level",
                "blocked_until",
                "updated_at",
            ]
        )
        return cooldown

    bucket.count += 1
    bucket.key_kind = identity.kind
    bucket.save(
        update_fields=[
            "key_kind",
            "window_seconds",
            "window_started_at",
            "expires_at",
            "count",
            "penalty_level",
            "blocked_until",
            "updated_at",
        ]
    )
    return 0


def enforce(scope: str, *, request=None, identifier=None, user=None, family_id=None) -> AbuseDecision:
    policy = get_policy(scope)
    identities = build_identity_keys(
        policy,
        request=request,
        identifier=identifier,
        user=user,
        family_id=family_id,
    )
    now = timezone.now()

    retry_after = 0
    blocked_by = ""
    with transaction.atomic():
        for identity in identities:
            for window_kind, window in (("burst", policy.burst), ("sustained", policy.sustained)):
                wait = _consume_bucket(
                    policy=policy,
                    identity=identity,
                    window_kind=window_kind,
                    window=window,
                    now=now,
                )
                if wait > retry_after:
                    retry_after = wait
                    blocked_by = identity.kind

    if retry_after:
        logger.warning(
            "auth_abuse_block category=%s scope=%s key_kind=%s retry_after=%s",
            policy.audit_category,
            policy.scope,
            blocked_by,
            retry_after,
        )
        prune_expired(now=now)
        return AbuseDecision(False, scope=scope, retry_after=retry_after, blocked_by=blocked_by)
    return AbuseDecision(True, scope=scope)


def forgive(scope: str, *, request=None, identifier=None, user=None, family_id=None, key_kinds: Iterable[str] = ("identifier", "network_identifier", "user")) -> None:
    policy = get_policy(scope)
    allowed_kinds = set(key_kinds)
    identities = [
        identity
        for identity in build_identity_keys(policy, request=request, identifier=identifier, user=user, family_id=family_id)
        if identity.kind in allowed_kinds
    ]
    if not identities:
        return

    with transaction.atomic():
        rows = AuthAbuseBucket.objects.select_for_update().filter(
            scope=scope,
            key_hash__in=[identity.digest for identity in identities],
        )
        for bucket in rows:
            bucket.count = 0
            bucket.penalty_level = 0
            bucket.blocked_until = None
            bucket.save(update_fields=["count", "penalty_level", "blocked_until", "updated_at"])


def prune_expired(*, now=None) -> int:
    now = now or timezone.now()
    retention_seconds = max(0, int(getattr(settings, "AUTH_ABUSE_RETENTION_SECONDS", 86400)))
    cutoff = now - timedelta(seconds=retention_seconds)
    deleted, _ = AuthAbuseBucket.objects.filter(expires_at__lt=cutoff).filter(
        Q(blocked_until__isnull=True) | Q(blocked_until__lte=now)
    ).delete()
    return deleted
