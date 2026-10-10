from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import AuthSession


class SessionUnavailable(APIException):
    status_code = 401
    default_detail = "Sitzung abgelaufen."
    default_code = "session_unavailable"


class FreshAuthenticationRequired(APIException):
    status_code = 403
    default_detail = "Bitte bestätige deine Identität erneut."
    default_code = "reauth_required"


class RefreshReuseDetected(SessionUnavailable):
    default_detail = "Sitzung wurde aus Sicherheitsgründen beendet."
    default_code = "refresh_reuse_detected"


@dataclass(frozen=True)
class RefreshRotationResult:
    session: AuthSession
    access: AccessToken | None
    refresh: RefreshToken | None
    parallel_conflict: bool = False


def _setting_int(name: str, default: int) -> int:
    return max(0, int(getattr(settings, name, default)))


def absolute_lifetime() -> timedelta:
    return timedelta(days=max(1, _setting_int("AUTH_SESSION_ABSOLUTE_DAYS", 90)))


def freshness_lifetime() -> timedelta:
    return timedelta(seconds=max(1, _setting_int("AUTH_SESSION_FRESH_SECONDS", 600)))


def refresh_reuse_grace() -> timedelta:
    return timedelta(seconds=_setting_int("AUTH_SESSION_REFRESH_REUSE_GRACE_SECONDS", 5))


def describe_client(request) -> str:
    ua = str(getattr(request, "META", {}).get("HTTP_USER_AGENT", "") or "")[:512]
    lowered = ua.lower()

    if "edg/" in lowered:
        browser = "Edge"
    elif "firefox/" in lowered or "fxios/" in lowered:
        browser = "Firefox"
    elif "crios/" in lowered or ("chrome/" in lowered and "edg/" not in lowered):
        browser = "Chrome"
    elif "safari/" in lowered and "chrome/" not in lowered and "crios/" not in lowered:
        browser = "Safari"
    else:
        browser = "Browser"

    if "iphone" in lowered:
        platform = "iPhone"
    elif "ipad" in lowered:
        platform = "iPad"
    elif "android" in lowered:
        platform = "Android"
    elif "mac os x" in lowered or "macintosh" in lowered:
        platform = "macOS"
    elif "windows" in lowered:
        platform = "Windows"
    elif "linux" in lowered:
        platform = "Linux"
    else:
        platform = "unbekanntem Gerät"
    return f"{browser} auf {platform}"[:120]


def _auth_time(session: AuthSession) -> int:
    return int(session.last_reauthenticated_at.timestamp())


def _remaining_lifetime(session: AuthSession, configured: timedelta, *, now=None) -> timedelta:
    now = now or timezone.now()
    remaining = session.absolute_expires_at - now
    if remaining.total_seconds() <= 0:
        raise SessionUnavailable()
    return min(configured, remaining)


def _decorate_token(token, session: AuthSession):
    token["sid"] = str(session.pk)
    token["auth_time"] = _auth_time(session)
    token["auth_method"] = session.auth_method
    return token


def issue_access_token(session: AuthSession, *, now=None) -> AccessToken:
    now = now or timezone.now()
    token = AccessToken.for_user(session.user)
    token.set_exp(from_time=now, lifetime=_remaining_lifetime(session, settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"], now=now))
    return _decorate_token(token, session)


def _new_refresh_pair(session: AuthSession, *, now=None) -> tuple[AccessToken, RefreshToken]:
    now = now or timezone.now()
    refresh = RefreshToken.for_user(session.user)
    refresh.set_exp(from_time=now, lifetime=_remaining_lifetime(session, settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"], now=now))
    _decorate_token(refresh, session)
    access = refresh.access_token
    access.set_exp(from_time=now, lifetime=_remaining_lifetime(session, settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"], now=now))
    _decorate_token(access, session)
    return access, refresh


def _token_expiry(token) -> datetime:
    return datetime.fromtimestamp(int(token["exp"]), tz=dt_timezone.utc)


def create_session(user, request, *, auth_method=AuthSession.AuthMethod.PASSWORD) -> tuple[AuthSession, AccessToken, RefreshToken]:
    now = timezone.now()
    session = AuthSession.objects.create(
        user=user,
        auth_method=auth_method,
        client_label=describe_client(request),
        last_seen_at=now,
        last_reauthenticated_at=now,
        absolute_expires_at=now + absolute_lifetime(),
        refresh_expires_at=now,
    )
    access, refresh = _new_refresh_pair(session, now=now)
    session.current_refresh_jti = str(refresh["jti"])
    session.refresh_expires_at = _token_expiry(refresh)
    session.save(update_fields=["current_refresh_jti", "refresh_expires_at"])
    return session, access, refresh


def _mark_revoked_locked(session: AuthSession, *, reason: str, now=None) -> None:
    now = now or timezone.now()
    if session.revoked_at is None:
        session.revoked_at = now
        session.revoked_reason = reason[:64]
        session.save(update_fields=["revoked_at", "revoked_reason"])


def revoke_session(session: AuthSession, *, reason: str) -> None:
    with transaction.atomic():
        locked = AuthSession.objects.select_for_update().filter(pk=session.pk).first()
        if locked is not None:
            _mark_revoked_locked(locked, reason=reason)


def revoke_all_user_sessions(user, *, reason: str, except_sid=None) -> int:
    now = timezone.now()
    queryset = AuthSession.objects.filter(user=user, revoked_at__isnull=True)
    if except_sid:
        queryset = queryset.exclude(pk=except_sid)
    return queryset.update(revoked_at=now, revoked_reason=reason[:64])


def revoke_from_refresh(raw_refresh: str | None, *, reason: str) -> bool:
    if not raw_refresh:
        return False
    try:
        token = RefreshToken(raw_refresh)
        sid = token.get("sid")
        user_id = token.get(api_settings.USER_ID_CLAIM)
    except TokenError:
        return False
    if not sid or user_id is None:
        return False
    with transaction.atomic():
        session = AuthSession.objects.select_for_update().filter(pk=sid, user_id=user_id).first()
        if session is None:
            return False
        _mark_revoked_locked(session, reason=reason)
        return True


def active_session_for_token(validated_token, *, touch=True) -> AuthSession:
    sid = validated_token.get("sid")
    user_id = validated_token.get(api_settings.USER_ID_CLAIM)
    if not sid or user_id is None:
        raise SessionUnavailable()

    now = timezone.now()
    session = AuthSession.objects.filter(pk=sid, user_id=user_id).first()
    if session is None or session.revoked_at is not None:
        raise SessionUnavailable()
    if session.absolute_expires_at <= now:
        AuthSession.objects.filter(pk=session.pk, revoked_at__isnull=True).update(
            revoked_at=now,
            revoked_reason="absolute_expiry",
        )
        raise SessionUnavailable()

    if touch:
        write_every = timedelta(seconds=max(30, _setting_int("AUTH_SESSION_SEEN_WRITE_SECONDS", 300)))
        if session.last_seen_at <= now - write_every:
            AuthSession.objects.filter(pk=session.pk, revoked_at__isnull=True).update(last_seen_at=now)
            session.last_seen_at = now
    return session


def rotate_refresh(raw_refresh: str) -> RefreshRotationResult:
    try:
        incoming = RefreshToken(raw_refresh)
    except TokenError as exc:
        raise SessionUnavailable() from exc

    sid = incoming.get("sid")
    user_id = incoming.get(api_settings.USER_ID_CLAIM)
    incoming_jti = str(incoming.get("jti") or "")
    if not sid or user_id is None or not incoming_jti:
        raise SessionUnavailable()

    now = timezone.now()
    compromised = False
    with transaction.atomic():
        session = AuthSession.objects.select_for_update().select_related("user").filter(pk=sid, user_id=user_id).first()
        if session is None or session.revoked_at is not None:
            raise SessionUnavailable()
        if session.absolute_expires_at <= now:
            _mark_revoked_locked(session, reason="absolute_expiry", now=now)
            expired = True
        else:
            expired = False

        if expired:
            result = None
        elif incoming_jti == session.current_refresh_jti:
            access, refresh = _new_refresh_pair(session, now=now)
            session.previous_refresh_jti = session.current_refresh_jti
            session.previous_refresh_valid_until = now + refresh_reuse_grace()
            session.current_refresh_jti = str(refresh["jti"])
            session.refresh_expires_at = _token_expiry(refresh)
            session.last_rotated_at = now
            session.last_seen_at = now
            session.save(
                update_fields=[
                    "previous_refresh_jti",
                    "previous_refresh_valid_until",
                    "current_refresh_jti",
                    "refresh_expires_at",
                    "last_rotated_at",
                    "last_seen_at",
                ]
            )
            result = RefreshRotationResult(session=session, access=access, refresh=refresh)
        elif (
            incoming_jti == session.previous_refresh_jti
            and session.previous_refresh_valid_until is not None
            and session.previous_refresh_valid_until >= now
        ):
            # A parallel tab may have sent the same cookie before the first
            # response rotated it. Do not mint a second refresh token and do not
            # revoke the session; the browser shares the cookie set by the winner.
            session.last_seen_at = now
            session.save(update_fields=["last_seen_at"])
            result = RefreshRotationResult(session=session, access=None, refresh=None, parallel_conflict=True)
        else:
            _mark_revoked_locked(session, reason="refresh_reuse", now=now)
            compromised = True
            result = None

    if expired:
        raise SessionUnavailable()
    if compromised:
        raise RefreshReuseDetected()
    return result


def is_fresh(session: AuthSession, *, now=None) -> bool:
    now = now or timezone.now()
    return session.revoked_at is None and session.last_reauthenticated_at >= now - freshness_lifetime()


def require_fresh_session(request) -> AuthSession:
    session = getattr(request, "auth_session", None)
    if session is None or not is_fresh(session):
        raise FreshAuthenticationRequired()
    return session


def mark_reauthenticated(session: AuthSession, *, auth_method=AuthSession.AuthMethod.PASSWORD) -> AuthSession:
    now = timezone.now()
    with transaction.atomic():
        locked = AuthSession.objects.select_for_update().get(pk=session.pk, user_id=session.user_id)
        if locked.revoked_at is not None or locked.absolute_expires_at <= now:
            raise SessionUnavailable()
        locked.last_reauthenticated_at = now
        locked.auth_method = auth_method
        locked.last_seen_at = now
        locked.save(update_fields=["last_reauthenticated_at", "auth_method", "last_seen_at"])
        return locked


def serialize_session(session: AuthSession, *, current_sid=None) -> dict:
    fresh_until = session.last_reauthenticated_at + freshness_lifetime()
    return {
        "id": str(session.pk),
        "current": str(session.pk) == str(current_sid) if current_sid else False,
        "client": session.client_label or "Browser",
        "auth_method": session.auth_method,
        "created_at": session.created_at,
        "last_seen_at": session.last_seen_at,
        "last_reauthenticated_at": session.last_reauthenticated_at,
        "fresh_until": fresh_until,
        "absolute_expires_at": session.absolute_expires_at,
    }


def active_sessions_for_user(user):
    now = timezone.now()
    return AuthSession.objects.filter(
        user=user,
        revoked_at__isnull=True,
        absolute_expires_at__gt=now,
    ).order_by("-last_seen_at", "-created_at")


def prune_old_sessions(*, now=None) -> int:
    now = now or timezone.now()
    retention_days = max(1, _setting_int("AUTH_SESSION_RETENTION_DAYS", 30))
    cutoff = now - timedelta(days=retention_days)
    deleted, _ = AuthSession.objects.filter(
        revoked_at__isnull=False,
        revoked_at__lt=cutoff,
    ).delete()
    deleted_expired, _ = AuthSession.objects.filter(
        revoked_at__isnull=True,
        absolute_expires_at__lt=cutoff,
    ).delete()
    return deleted + deleted_expired
