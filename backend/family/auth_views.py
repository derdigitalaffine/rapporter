from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from auth_abuse.service import enforce, forgive

from .authentication import ACCESS_COOKIE, REFRESH_COOKIE


LOGIN_FAILURE_DETAIL = "Anmeldung fehlgeschlagen."


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

    data = serializer.validated_data
    forgive("login.password", request=request, identifier=identifier)
    response = Response({"authenticated": True})
    return set_token_cookies(response, data["access"], data["refresh"])


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
    return Response(
        {
            "authenticated": True,
            "user": {
                "id": request.user.pk,
                "username": request.user.username,
                "email": request.user.email,
                "is_superadmin": bool(request.user.is_superuser),
            },
        }
    )
