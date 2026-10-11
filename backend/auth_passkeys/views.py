from rest_framework import permissions, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from auth_abuse.service import enforce, forgive
from auth_identity.service import identity_summary
from auth_sessions.cookies import set_token_cookies
from auth_sessions.service import require_fresh_session, serialize_session

from .models import WebAuthnChallenge, WebAuthnCredential
from .service import (
    authentication_options,
    complete_authentication,
    complete_reauthentication,
    complete_registration,
    registration_options,
    rename_credential,
    revoke_credential,
    serialize_credential,
)


def _rate_limited(decision):
    response = Response(
        {
            "detail": "Passkey-Anfrage vorübergehend begrenzt.",
            "code": "rate_limited",
            "retry_after": decision.retry_after,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(decision.retry_after)
    return response


def _enforce(scope, request, *, identifier=None):
    decision = enforce(scope, request=request, identifier=identifier, user=getattr(request, "user", None))
    if decision.allowed:
        return None
    return _rate_limited(decision)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def passkey_list(request):
    credentials = WebAuthnCredential.objects.filter(
        user=request.user,
        revoked_at__isnull=True,
    )
    return Response({"results": [serialize_credential(item) for item in credentials]})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def registration_options_view(request):
    require_fresh_session(request)
    limited = _enforce("webauthn.registration.options", request)
    if limited:
        return limited
    return Response(registration_options(request.user))


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def registration_verify_view(request):
    require_fresh_session(request)
    limited = _enforce("webauthn.registration.options", request)
    if limited:
        return limited
    credential = complete_registration(
        request.user,
        challenge_id=request.data.get("challenge_id"),
        credential=request.data.get("credential") or {},
        name=request.data.get("name") or "",
    )
    return Response(serialize_credential(credential), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def authentication_options_view(request):
    limited = _enforce("login.passkey.options", request)
    if limited:
        return limited
    return Response(authentication_options())


@api_view(["POST"])
@authentication_classes([])
@permission_classes([permissions.AllowAny])
def authentication_verify_view(request):
    limited = _enforce("login.passkey.verify", request)
    if limited:
        return limited
    stored, session, access, refresh = complete_authentication(
        request,
        challenge_id=request.data.get("challenge_id"),
        credential=request.data.get("credential") or {},
    )
    forgive("login.passkey.options", request=request)
    forgive("login.passkey.verify", request=request)
    summary = identity_summary(stored.user)
    response = Response(
        {
            "authenticated": True,
            "email_verified": summary["email_verified"],
            "email_action_required": summary["email_action_required"],
            "session": serialize_session(session, current_sid=session.pk),
        }
    )
    return set_token_cookies(response, access, refresh)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def reauthentication_options_view(request):
    limited = _enforce("login.passkey.options", request, identifier=str(request.user.pk))
    if limited:
        return limited
    return Response(
        authentication_options(
            user=request.user,
            ceremony=WebAuthnChallenge.Ceremony.REAUTHENTICATE,
        )
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def reauthentication_verify_view(request):
    limited = _enforce("login.passkey.verify", request, identifier=str(request.user.pk))
    if limited:
        return limited
    stored = complete_reauthentication(
        request,
        challenge_id=request.data.get("challenge_id"),
        credential=request.data.get("credential") or {},
    )
    forgive("login.passkey.options", request=request, identifier=str(request.user.pk))
    forgive("login.passkey.verify", request=request, identifier=str(request.user.pk))
    return Response({"reauthenticated": True, "credential": serialize_credential(stored)})


@api_view(["PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def passkey_detail(request, credential_id):
    require_fresh_session(request)
    if request.method == "PATCH":
        credential = rename_credential(
            request.user,
            credential_id,
            name=request.data.get("name") or "",
        )
        return Response(serialize_credential(credential))
    revoke_credential(request.user, credential_id)
    return Response(status=status.HTTP_204_NO_CONTENT)
