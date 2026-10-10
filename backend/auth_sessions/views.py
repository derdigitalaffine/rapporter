from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth_abuse.service import enforce

from .cookies import set_access_cookie
from .models import AuthSession
from .service import (
    active_sessions_for_user,
    issue_access_token,
    mark_reauthenticated,
    require_fresh_session,
    revoke_all_user_sessions,
    revoke_session,
    serialize_session,
)


REAUTH_FAILURE_DETAIL = "Bestätigung fehlgeschlagen."


def _rate_limited_response(decision):
    response = Response(
        {
            "detail": REAUTH_FAILURE_DETAIL,
            "code": "rate_limited",
            "retry_after": decision.retry_after,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(decision.retry_after)
    return response


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def session_list(request):
    current = getattr(request, "auth_session", None)
    current_sid = current.pk if current else None
    rows = [serialize_session(item, current_sid=current_sid) for item in active_sessions_for_user(request.user)]
    return Response({"sessions": rows, "fresh": bool(current and current.last_reauthenticated_at + __freshness_delta() > timezone.now())})


def __freshness_delta():
    # Kept local to avoid exposing configuration details in the API surface.
    from .service import freshness_lifetime

    return freshness_lifetime()


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def session_detail(request, sid):
    current = getattr(request, "auth_session", None)
    if current is not None and str(current.pk) == str(sid):
        return Response(
            {"detail": "Die aktuelle Sitzung wird über Abmelden beendet.", "code": "current_session"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target = AuthSession.objects.filter(pk=sid, user=request.user).first()
    if target is not None:
        revoke_session(target, reason="user_revoked")
    # Deliberately identical for missing and cross-user ids.
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def revoke_other_sessions(request):
    current = require_fresh_session(request)
    revoked = revoke_all_user_sessions(
        request.user,
        reason="revoke_others",
        except_sid=current.pk,
    )
    return Response({"revoked": revoked})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def reauthenticate_password(request):
    current = getattr(request, "auth_session", None)
    decision = enforce("reauth.password", request=request, user=request.user)
    if not decision.allowed:
        return _rate_limited_response(decision)

    password = request.data.get("password") or ""
    if not password or not request.user.check_password(password):
        return Response(
            {"detail": REAUTH_FAILURE_DETAIL, "code": "reauth_failed"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    if current is None:
        return Response({"detail": "Keine aktive Sitzung."}, status=status.HTTP_401_UNAUTHORIZED)

    current = mark_reauthenticated(current, auth_method=AuthSession.AuthMethod.PASSWORD)
    access = issue_access_token(current)
    payload = serialize_session(current, current_sid=current.pk)
    response = Response({"reauthenticated": True, "session": payload})
    return set_access_cookie(response, access)
