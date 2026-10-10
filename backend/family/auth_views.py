import logging

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from auth_abuse.service import enforce, forgive
from auth_identity.service import authenticate_identifier, identity_summary

from .authentication import ACCESS_COOKIE, REFRESH_COOKIE


LOGIN_FAILURE_DETAIL = "Anmeldung fehlgeschlagen."
logger = logging.getLogger("security.auth_identity")


def _cookie_secure():
    return not settings.DEBUG


def set_token_cookies(response, access, refresh=None):
    response.set_cookie(
        ACCESS_COOKIE,
        str(access),
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=_cookie_secure(),
        samesite="Lax",
        path="/",
    )
    if refresh is not None:
        response.set_cookie(
            REFRESH_COOKIE,
            str(refresh),
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            httponly=True,
            secure=_cookie_secure(),
            samesite="Lax",
            path="/",
        )
    return response


def set_user_cookies(response, user):
    refresh = RefreshToken.for_user(user)
    return set_token_cookies(response, refresh.access_token, refresh)


def clear_token_cookies(response):
    response.delete_cookie(ACCESS_COOKIE, path="/", samesite="Lax")
    response.delete_cookie(REFRESH_COOKIE, path="/", samesite="Lax")
    return response


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
    return set_user_cookies(response, user)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def refresh_view(request):
    refresh = request.COOKIES.get(REFRESH_COOKIE)
    if not refresh:
        return Response({"detail": "Keine aktive Sitzung."}, status=status.HTTP_401_UNAUTHORIZED)
    serializer = TokenRefreshSerializer(data={"refresh": refresh})
    try:
        serializer.is_valid(raise_exception=True)
    except Exception:
        response = Response({"detail": "Sitzung abgelaufen."}, status=status.HTTP_401_UNAUTHORIZED)
        return clear_token_cookies(response)
    data = serializer.validated_data
    response = Response({"authenticated": True})
    return set_token_cookies(response, data["access"], data.get("refresh"))


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def logout_view(request):
    response = Response({"authenticated": False})
    return clear_token_cookies(response)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def session_view(request):
    email = identity_summary(request.user)
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
        }
    )
