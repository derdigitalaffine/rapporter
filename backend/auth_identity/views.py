from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth_abuse.service import enforce, forgive

from .models import EmailIdentity
from .service import (
    EmailConflictError,
    EmailIdentityError,
    EmailVerificationError,
    identity_summary,
    pending_identity,
    primary_identity,
    queue_verification,
    request_pending_email,
    verify_email_token,
)


def _locale(request):
    language = request.headers.get("Accept-Language", "")
    return "en" if language.lower().startswith("en") else "de"


def _rate_limited(decision_or_seconds):
    retry_after = int(getattr(decision_or_seconds, "retry_after", decision_or_seconds) or 1)
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


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def identity_status(request):
    return Response(identity_summary(request.user))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def resend_verification(request):
    target = str(request.data.get("target") or "primary").lower()
    identity = pending_identity(request.user) if target == "pending" else primary_identity(request.user)
    if not identity or identity.verified_at:
        return Response({"detail": "Für diese Adresse ist keine Bestätigung erforderlich."}, status=status.HTTP_400_BAD_REQUEST)

    decision = enforce(
        "email_verification.resend",
        request=request,
        user=request.user,
        identifier=identity.email_normalized,
    )
    if not decision.allowed:
        return _rate_limited(decision)

    cooldown = max(0, int(getattr(settings, "EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS", 60)))
    if identity.verification_sent_at and cooldown:
        available_at = identity.verification_sent_at + timedelta(seconds=cooldown)
        if available_at > timezone.now():
            return _rate_limited((available_at - timezone.now()).total_seconds())

    queue_verification(identity, locale=_locale(request))
    return Response({"sent": True})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def change_email(request):
    password = request.data.get("password") or ""
    decision = enforce("reauth.password", request=request, user=request.user)
    if not decision.allowed:
        return _rate_limited(decision)
    if not request.user.check_password(password):
        return Response({"detail": "Erneute Anmeldung fehlgeschlagen."}, status=status.HTTP_403_FORBIDDEN)
    forgive("reauth.password", request=request, user=request.user)

    try:
        pending = request_pending_email(request.user, request.data.get("email") or "")
        pending = queue_verification(pending, locale=_locale(request))
    except (EmailConflictError, EmailIdentityError):
        return Response(
            {"detail": "Diese E-Mail-Adresse kann nicht verwendet werden."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response(
        {
            "pending_email": pending.email,
            "verification_sent_at": pending.verification_sent_at,
        },
        status=status.HTTP_202_ACCEPTED,
    )


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def verify_email(request):
    try:
        identity, changed = verify_email_token(request.data.get("token") or "")
    except EmailVerificationError:
        return Response(
            {"detail": "Bestätigungslink ist ungültig oder abgelaufen."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({"verified": True, "changed": changed, "kind": identity.kind})
