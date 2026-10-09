from django.conf import settings
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .authentication import ACCESS_COOKIE, REFRESH_COOKIE


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


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def login_view(request):
    serializer = TokenObtainPairSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
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
def session_view(request):
    return Response({
        "authenticated": True,
        "user": {
            "id": request.user.pk,
            "username": request.user.username,
            "email": request.user.email,
            "is_superadmin": bool(request.user.is_superuser),
        },
    })
