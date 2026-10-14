from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth_passkeys.models import WebAuthnChallenge, WebAuthnCredential
from auth_passkeys.service import (
    authentication_options,
    complete_reauthentication,
    complete_registration,
    registration_options,
    rename_credential,
    revoke_credential,
    serialize_credential,
)
from telemetry.service import try_record_audit_event

from .admin_views import IsSuperAdminSession
from .cookies import set_admin_access_cookie
from .models import AuthSession
from .service import (
    issue_access_token,
    require_fresh_session,
    revoke_all_user_sessions,
    serialize_session,
)

SUPERADMIN_CONTEXT = WebAuthnChallenge.Context.SUPERADMIN


def _audit(event_key, request, *, target_type="superadmin_account", target_id=None, reason=""):
    try_record_audit_event(
        event_key,
        actor=request.user,
        actor_class="superadmin",
        outcome="success",
        reason=reason,
        target_type=target_type,
        target_id=str(target_id or request.user.pk),
        metadata={"surface": "superadmin"},
    )


@api_view(["GET"])
@permission_classes([IsSuperAdminSession])
def superadmin_passkeys(request):
    credentials = WebAuthnCredential.objects.filter(
        user=request.user,
        surface=WebAuthnCredential.Surface.SUPERADMIN,
        revoked_at__isnull=True,
    )
    return Response({"results": [serialize_credential(item) for item in credentials]})


@api_view(["POST"])
@permission_classes([IsSuperAdminSession])
def superadmin_passkey_registration_options(request):
    require_fresh_session(request)
    return Response(registration_options(request.user, context=SUPERADMIN_CONTEXT))


@api_view(["POST"])
@permission_classes([IsSuperAdminSession])
def superadmin_passkey_registration_verify(request):
    require_fresh_session(request)
    credential = complete_registration(
        request.user,
        challenge_id=request.data.get("challenge_id"),
        credential=request.data.get("credential") or {},
        name=request.data.get("name") or "",
        context=SUPERADMIN_CONTEXT,
    )
    _audit(
        "auth.passkey.registered",
        request,
        target_type="superadmin_passkey",
        target_id=credential.pk,
    )
    return Response(serialize_credential(credential), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsSuperAdminSession])
def superadmin_passkey_detail(request, credential_id):
    require_fresh_session(request)
    if request.method == "PATCH":
        credential = rename_credential(
            request.user,
            credential_id,
            name=request.data.get("name") or "",
            context=SUPERADMIN_CONTEXT,
        )
        return Response(serialize_credential(credential))

    revoke_credential(request.user, credential_id, context=SUPERADMIN_CONTEXT)
    _audit(
        "auth.passkey.removed",
        request,
        target_type="superadmin_passkey",
        target_id=credential_id,
        reason="superadmin_request",
    )
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsSuperAdminSession])
def superadmin_passkey_reauthentication_options(request):
    return Response(
        authentication_options(
            user=request.user,
            ceremony=WebAuthnChallenge.Ceremony.REAUTHENTICATE,
            context=SUPERADMIN_CONTEXT,
        )
    )


@api_view(["POST"])
@permission_classes([IsSuperAdminSession])
def superadmin_passkey_reauthentication_verify(request):
    stored = complete_reauthentication(
        request,
        challenge_id=request.data.get("challenge_id"),
        credential=request.data.get("credential") or {},
        context=SUPERADMIN_CONTEXT,
    )
    current = request.auth_session
    if current.surface != AuthSession.Surface.SUPERADMIN:
        return Response({"detail": "Keine aktive Admin-Sitzung."}, status=status.HTTP_401_UNAUTHORIZED)
    access = issue_access_token(current)
    response = Response(
        {
            "reauthenticated": True,
            "credential": serialize_credential(stored),
            "session": serialize_session(current, current_sid=current.pk),
        }
    )
    return set_admin_access_cookie(response, access)


@api_view(["PUT"])
@permission_classes([IsSuperAdminSession])
def superadmin_password_change(request):
    current = require_fresh_session(request)
    new_password = str(request.data.get("new_password") or "")
    confirm_password = str(request.data.get("confirm_password") or "")
    if new_password != confirm_password:
        return Response(
            {"detail": "Die Passwörter stimmen nicht überein.", "code": "password_mismatch"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        validate_password(new_password, user=request.user)
    except ValidationError as exc:
        return Response(
            {"detail": " ".join(exc.messages), "code": "password_invalid"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    request.user.set_password(new_password)
    request.user.save(update_fields=["password"])
    revoke_all_user_sessions(request.user, reason="password_changed", except_sid=current.pk)
    _audit("auth.password.changed", request, reason="superadmin_self_service")
    access = issue_access_token(current)
    response = Response(
        {
            "changed": True,
            "session": serialize_session(current, current_sid=current.pk),
        }
    )
    return set_admin_access_cookie(response, access)
