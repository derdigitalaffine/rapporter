import logging

from rest_framework import permissions, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from auth_abuse.service import enforce, forgive
from auth_identity.service import authenticate_identifier, identity_summary
from auth_sessions.cookies import REFRESH_COOKIE, clear_token_cookies, set_token_cookies
from auth_sessions.models import AuthSession
from auth_sessions.service import (
    SessionUnavailable,
    create_session,
    revoke_from_refresh,
    rotate_refresh,
    serialize_session,
)

LOGIN_FAILURE_DETAIL = "Anmeldung fehlgeschlagen."
logger = logging.getLogger("security.auth_identity")


def set_user_cookies(response, user, request=None, *, auth_method=AuthSession.AuthMethod.PASSWORD):
    session, access, refresh = create_session(user, request, auth_method=auth_method)
    set_token_cookies(response, access, refresh)
    return response, session


def _login_payload(request):
    # During the migration window old clients may still send only `username`.
    # The identity service allows that path only for superadmins or accounts
    # without a primary email identity, so it cannot become a hidden second
    # login identifier for newly migrated normal users.
    legacy = bool(request.data.get("legacy")) or (
        "email" not in request.data and bool(request.data.get("username"))
    )
    identifier = request.data.get("username") if legacy else request.data.get("email")
    return str(identifier or ""), legacy


def _rate_limited_login_response(decision):
    response = Response(
        {
            "detail": LOGIN_FAILURE_DETAIL,
            "code": "rate_limited",
            "retry_after": decision.retry_after,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(decision.retry_after)
    return response


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def login_view(request):
    identifier, legacy = _login_payload(request)
    decision = enforce("login.password", request=request, identifier=identifier)
    if not decision.allowed:
        return _rate_limited_login_response(decision)

    user = authenticate_identifier(identifier, request.data.get("password") or "", legacy=legacy)
    if not user:
        logger.info("auth_login result=failure identity=%s", "legacy" if legacy else "email")
        return Response({"detail": LOGIN_FAILURE_DETAIL}, status=status.HTTP_401_UNAUTHORIZED)

    forgive("login.password", request=request, identifier=identifier)
    summary = identity_summary(user)
    logger.info(
        "auth_login result=success identity=%s user_id=%s",
        "legacy" if legacy else "email",
        user.pk,
    )
    response = Response(
        {
            "authenticated": True,
            "email_verified": summary["email_verified"],
            "email_action_required": summary["email_action_required"],
        }
    )
    response, session = set_user_cookies(response, user, request=request)
    response.data["session"] = serialize_session(session, current_sid=session.pk)
    return response


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def refresh_view(request):
    raw_refresh = request.COOKIES.get(REFRESH_COOKIE)
    if not raw_refresh:
        return Response({"detail": "Keine aktive Sitzung."}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        result = rotate_refresh(raw_refresh)
    except SessionUnavailable as exc:
        response = Response(
            {"detail": str(exc.detail), "code": exc.get_codes()},
            status=status.HTTP_401_UNAUTHORIZED,
        )
        return clear_token_cookies(response)

    if result.parallel_conflict:
        return Response({"authenticated": True, "parallel_refresh": True})

    response = Response({"authenticated": True})
    return set_token_cookies(response, result.access, result.refresh)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def logout_view(request):
    revoke_from_refresh(request.COOKIES.get(REFRESH_COOKIE), reason="logout")
    response = Response({"authenticated": False})
    return clear_token_cookies(response)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def session_view(request):
    email = identity_summary(request.user)
    session = getattr(request, "auth_session", None)
    return Response(
        {
            "authenticated": True,
            "user": {
                "id": request.user.pk,
                "username": request.user.username,
                "email": email["email"] or request.user.email,
                "email_verified": email["email_verified"],
                "email_action_required": email["email_action_required"],
                "pending_email": email["pending_email"],
                "is_superadmin": bool(request.user.is_superuser),
            },
            "session": serialize_session(session, current_sid=session.pk) if session else None,
        }
    )
