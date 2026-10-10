from django.contrib.auth import get_user_model
from rest_framework import permissions, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from auth_abuse.service import enforce, forgive
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


def set_user_cookies(response, user, request=None, *, auth_method=AuthSession.AuthMethod.PASSWORD):
    session, access, refresh = create_session(user, request, auth_method=auth_method)
    set_token_cookies(response, access, refresh)
    return response, session


def _login_identifier(request):
    username_field = get_user_model().USERNAME_FIELD
    return request.data.get(username_field) or request.data.get("username") or request.data.get("email") or ""


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
    identifier = _login_identifier(request)
    decision = enforce("login.password", request=request, identifier=identifier)
    if not decision.allowed:
        return _rate_limited_login_response(decision)

    serializer = TokenObtainPairSerializer(data=request.data)
    try:
        serializer.is_valid(raise_exception=True)
    except APIException:
        # Do not expose whether an identifier exists, is inactive, or merely has
        # a wrong password. Rate-limit keys behave identically for all values.
        return Response({"detail": LOGIN_FAILURE_DETAIL}, status=status.HTTP_401_UNAUTHORIZED)

    forgive("login.password", request=request, identifier=identifier)
    response = Response({"authenticated": True})
    response, session = set_user_cookies(response, serializer.user, request)
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
        # Another same-browser tab won the row lock and already rotated the
        # shared cookie. Returning success without a second rotation avoids a
        # false-positive compromise response.
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
    session = getattr(request, "auth_session", None)
    return Response(
        {
            "authenticated": True,
            "user": {
                "id": request.user.pk,
                "username": request.user.username,
                "email": request.user.email,
                "is_superadmin": bool(request.user.is_superuser),
            },
            "session": serialize_session(session, current_sid=session.pk) if session else None,
        }
    )
