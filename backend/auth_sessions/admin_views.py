import logging

from rest_framework import permissions, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from auth_abuse.service import enforce, forgive
from auth_identity.service import authenticate_identifier, identity_summary

from .cookies import (
    ADMIN_REFRESH_COOKIE,
    clear_admin_token_cookies,
    set_admin_access_cookie,
    set_admin_token_cookies,
)
from .models import AuthSession
from .service import (
    SessionUnavailable,
    active_sessions_for_user,
    create_session,
    is_fresh,
    issue_access_token,
    mark_reauthenticated,
    revoke_from_refresh,
    rotate_refresh,
    serialize_session,
)

LOGIN_FAILURE_DETAIL = "Anmeldung fehlgeschlagen."
REAUTH_FAILURE_DETAIL = "Bestätigung fehlgeschlagen."
logger = logging.getLogger("security.superadmin_auth")


class IsSuperAdminSession(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


def _rate_limited(decision, detail):
    response = Response(
        {"detail": detail, "code": "rate_limited", "retry_after": decision.retry_after},
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(decision.retry_after)
    return response


def _user_payload(user):
    identity = identity_summary(user)
    return {
        "id": user.pk,
        "username": user.username,
        "email": identity["email"] or user.email,
        "email_verified": identity["email_verified"],
        "is_superadmin": True,
    }


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def superadmin_login(request):
    identifier = str(
        request.data.get("identifier")
        or request.data.get("email")
        or request.data.get("username")
        or ""
    ).strip()
    password = request.data.get("password") or ""
    decision = enforce("login.password", request=request, identifier=identifier)
    if not decision.allowed:
        return _rate_limited(decision, LOGIN_FAILURE_DETAIL)

    legacy = "@" not in identifier
    user = authenticate_identifier(identifier, password, legacy=legacy)
    if not user or not user.is_active or not user.is_superuser:
        logger.info("superadmin_login result=failure")
        return Response({"detail": LOGIN_FAILURE_DETAIL}, status=status.HTTP_401_UNAUTHORIZED)

    forgive("login.password", request=request, identifier=identifier)
    session, access, refresh = create_session(user, request, auth_method=AuthSession.AuthMethod.PASSWORD)
    response = Response(
        {
            "authenticated": True,
            "user": _user_payload(user),
            "session": serialize_session(session, current_sid=session.pk),
        }
    )
    logger.info("superadmin_login result=success user_id=%s", user.pk)
    return set_admin_token_cookies(response, access, refresh)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def superadmin_refresh(request):
    raw_refresh = request.COOKIES.get(ADMIN_REFRESH_COOKIE)
    if not raw_refresh:
        return Response({"detail": "Keine aktive Admin-Sitzung."}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        result = rotate_refresh(raw_refresh)
    except SessionUnavailable as exc:
        response = Response(
            {"detail": str(exc.detail), "code": exc.get_codes()},
            status=status.HTTP_401_UNAUTHORIZED,
        )
        return clear_admin_token_cookies(response)

    if result.parallel_conflict:
        return Response({"authenticated": True, "parallel_refresh": True})
    response = Response({"authenticated": True})
    return set_admin_token_cookies(response, result.access, result.refresh)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def superadmin_logout(request):
    revoke_from_refresh(request.COOKIES.get(ADMIN_REFRESH_COOKIE), reason="admin_logout")
    response = Response({"authenticated": False})
    return clear_admin_token_cookies(response)


@api_view(["GET"])
@permission_classes([IsSuperAdminSession])
def superadmin_session(request):
    current = getattr(request, "auth_session", None)
    return Response(
        {
            "authenticated": True,
            "user": _user_payload(request.user),
            "session": serialize_session(current, current_sid=current.pk) if current else None,
            "fresh": bool(current and is_fresh(current)),
        }
    )


@api_view(["GET"])
@permission_classes([IsSuperAdminSession])
def superadmin_sessions(request):
    current = getattr(request, "auth_session", None)
    current_sid = current.pk if current else None
    rows = [serialize_session(item, current_sid=current_sid) for item in active_sessions_for_user(request.user)]
    return Response({"sessions": rows, "fresh": bool(current and is_fresh(current))})


@api_view(["POST"])
@permission_classes([IsSuperAdminSession])
def superadmin_reauthenticate_password(request):
    current = getattr(request, "auth_session", None)
    decision = enforce("reauth.password", request=request, user=request.user)
    if not decision.allowed:
        return _rate_limited(decision, REAUTH_FAILURE_DETAIL)

    password = request.data.get("password") or ""
    if not password or not request.user.check_password(password):
        return Response(
            {"detail": REAUTH_FAILURE_DETAIL, "code": "reauth_failed"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if current is None:
        return Response({"detail": "Keine aktive Admin-Sitzung."}, status=status.HTTP_401_UNAUTHORIZED)

    current = mark_reauthenticated(current, auth_method=AuthSession.AuthMethod.PASSWORD)
    access = issue_access_token(current)
    response = Response(
        {"reauthenticated": True, "session": serialize_session(current, current_sid=current.pk)}
    )
    return set_admin_access_cookie(response, access)
