from django.core.exceptions import ValidationError
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth_abuse.service import enforce

from .password_reset import PasswordResetError, complete_password_reset, request_password_reset


def _locale(request):
    language = request.headers.get("Accept-Language", "")
    return "en" if language.lower().startswith("en") else "de"


def _request_accepted(locale):
    detail = (
        "If an eligible account exists for this email address, a reset link has been sent."
        if locale == "en"
        else "Wenn für diese E-Mail-Adresse ein berechtigtes Konto existiert, wurde ein Reset-Link versendet."
    )
    return Response({"accepted": True, "detail": detail}, status=status.HTTP_202_ACCEPTED)


def _rate_limited(decision):
    retry_after = int(getattr(decision, "retry_after", 1) or 1)
    response = Response(
        {
            "detail": "Zu viele Anfragen. Bitte später erneut versuchen.",
            "code": "rate_limited",
            "retry_after": retry_after,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(retry_after)
    return response


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def password_reset_request(request):
    email = request.data.get("email") or ""
    decision = enforce(
        "password_reset.request",
        request=request,
        identifier=email,
    )
    if not decision.allowed:
        return _rate_limited(decision)

    locale = _locale(request)
    request_password_reset(email, locale=locale)
    return _request_accepted(locale)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def password_reset_confirm(request):
    locale = _locale(request)
    try:
        complete_password_reset(
            request.data.get("uid") or "",
            request.data.get("token") or "",
            request.data.get("password") or "",
            locale=locale,
        )
    except PasswordResetError:
        detail = (
            "This reset link is invalid or has expired."
            if locale == "en"
            else "Dieser Reset-Link ist ungültig oder abgelaufen."
        )
        return Response(
            {"detail": detail, "code": "invalid_or_expired"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ValidationError as exc:
        detail = (
            "The new password does not meet the security requirements."
            if locale == "en"
            else "Das neue Passwort erfüllt die Sicherheitsanforderungen nicht."
        )
        return Response(
            {"detail": detail, "code": "password_invalid", "errors": list(exc.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({"changed": True})
