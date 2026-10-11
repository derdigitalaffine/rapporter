from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth_identity.models import EmailIdentity
from auth_identity.password_reset import create_password_reset_reference, password_reset_path, request_password_reset
from auth_identity.service import (
    EmailConflictError,
    EmailIdentityError,
    queue_verification,
    request_pending_email,
    set_primary_email_direct,
)
from telemetry.models import AuditEvent
from telemetry.service import try_record_audit_event

from .models import FamilyInvitation
from .superadmin_views import IsSuperAdmin, _enforce_sensitive_action, _rate_limited_response


MAX_PAGE_SIZE = 200
USER_DETAIL_SESSION_LIMIT = 50
USER_DETAIL_AUDIT_LIMIT = 50
USER_DETAIL_INVITE_LIMIT = 50
SAFE_AUTH_METHODS = {"password", "passkey", "recovery", "legacy"}
USER_SORTS = {
    "username": ("username", "pk"),
    "-username": ("-username", "pk"),
    "created_at": ("date_joined", "pk"),
    "-created_at": ("-date_joined", "pk"),
    "last_activity": ("last_activity_at", "pk"),
    "-last_activity": ("-last_activity_at", "pk"),
    "last_login": ("last_login_at", "pk"),
    "-last_login": ("-last_login_at", "pk"),
    "families": ("family_count", "pk"),
    "-families": ("-family_count", "pk"),
}
USER_STATUSES = {"active": True, "inactive": False}


def _bounded_int(value, *, default, minimum=0, maximum=MAX_PAGE_SIZE):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _user_row(user):
    identities = list(user.email_identities.all())
    primary = next((item for item in identities if item.kind == EmailIdentity.Kind.PRIMARY), None)
    pending = next((item for item in identities if item.kind == EmailIdentity.Kind.PENDING), None)
    memberships = sorted(list(user.family_memberships.all()), key=lambda item: (item.family.name.casefold(), str(item.id)))
    display_name = next((item.display_name for item in memberships if item.display_name), "")
    if not display_name:
        display_name = user.get_full_name().strip() or user.username
    visible_email = primary.email if primary else str(user.email or "")
    active_passkeys = int(getattr(user, "active_passkeys", 0) or 0)
    return {
        "id": user.pk,
        "username": user.username,
        "display_name": display_name,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "email": visible_email,
        "email_verified": bool(primary and primary.verified_at),
        "email_managed": primary is not None,
        "pending_email": pending.email if pending else "",
        "pending_verification_sent_at": pending.verification_sent_at if pending else None,
        "can_password_reset": bool(user.is_active and primary and primary.verified_at),
        "created_at": user.date_joined,
        "last_activity_at": getattr(user, "last_activity_at", None),
        "last_login_at": getattr(user, "last_login_at", None),
        "family_count": int(getattr(user, "family_count", len(memberships)) or 0),
        "active_sessions": int(getattr(user, "active_sessions", 0) or 0),
        "auth_methods": {
            "password": user.has_usable_password(),
            "passkeys": active_passkeys,
        },
        "memberships": [
            {
                "id": str(item.id),
                "family_id": str(item.family_id),
                "family_name": item.family.name,
                "family_status": item.family.status,
                "role": item.role,
                "display_name": item.display_name,
            }
            for item in memberships
        ],
    }


def _users_queryset():
    now = timezone.now()
    return (
        get_user_model()
        .objects.prefetch_related("email_identities", "family_memberships__family")
        .annotate(
            last_activity_at=Max("usage_events__occurred_at"),
            last_login_at=Max(
                "audit_events__occurred_at",
                filter=Q(audit_events__event_key="auth.login.succeeded"),
            ),
            family_count=Count("family_memberships", distinct=True),
            active_sessions=Count(
                "auth_sessions",
                distinct=True,
                filter=Q(
                    auth_sessions__revoked_at__isnull=True,
                    auth_sessions__absolute_expires_at__gt=now,
                ),
            ),
            active_passkeys=Count(
                "webauthn_credentials",
                distinct=True,
                filter=Q(webauthn_credentials__revoked_at__isnull=True),
            ),
        )
    )


def _target_user(user_id):
    return _users_queryset().filter(pk=user_id).first()


def _user_locale(user):
    membership = next(iter(user.family_memberships.all()), None)
    return "en" if membership and str(membership.family.locale).lower().startswith("en") else "de"


def _absolute_admin_url(request, path):
    forwarded_proto = str(request.headers.get("X-Forwarded-Proto") or "").split(",", 1)[0].strip().lower()
    scheme = forwarded_proto if forwarded_proto in {"http", "https"} else request.scheme
    return f"{scheme}://{request.get_host()}{path}"


def _invite_state(invite, now):
    if invite.accepted_at is not None:
        return "accepted"
    if invite.revoked_at is not None:
        return "revoked"
    if invite.expires_at <= now:
        return "expired"
    return "pending"


def _safe_auth_method(metadata):
    value = str((metadata or {}).get("auth_method") or "").strip().lower()
    return value if value in SAFE_AUTH_METHODS else None


def _user_detail_payload(user):
    now = timezone.now()
    active_sessions = list(
        user.auth_sessions.filter(
            revoked_at__isnull=True,
            absolute_expires_at__gt=now,
        ).order_by("-last_seen_at", "-created_at")[:USER_DETAIL_SESSION_LIMIT]
    )
    active_passkeys = user.webauthn_credentials.filter(revoked_at__isnull=True)
    revoked_passkeys = user.webauthn_credentials.filter(revoked_at__isnull=False)

    audit_rows = list(
        AuditEvent.objects.filter(actor=user, event_key__startswith="auth.")
        .order_by("-occurred_at", "id")
        .values(
            "occurred_at",
            "event_key",
            "outcome",
            "reason",
            "family_id",
            "target_type",
            "metadata",
        )[:USER_DETAIL_AUDIT_LIMIT]
    )
    auth_timeline = [
        {
            "occurred_at": row["occurred_at"],
            "event_key": row["event_key"],
            "outcome": row["outcome"],
            "reason": row["reason"],
            "family_id": str(row["family_id"]) if row["family_id"] else None,
            "target_type": row["target_type"],
            "auth_method": _safe_auth_method(row["metadata"]),
        }
        for row in audit_rows
    ]
    last_successful_auth_method = next(
        (
            row["auth_method"]
            for row in auth_timeline
            if row["event_key"] == "auth.login.succeeded" and row["outcome"] == AuditEvent.Outcome.SUCCESS
        ),
        None,
    )

    identity_emails = {
        str(identity.email or "").strip().casefold()
        for identity in user.email_identities.all()
        if str(identity.email or "").strip()
    }
    if str(user.email or "").strip():
        identity_emails.add(str(user.email).strip().casefold())
    invite_filter = Q(accepted_by=user)
    for email in identity_emails:
        invite_filter |= Q(email__iexact=email)
    invites = list(
        FamilyInvitation.objects.select_related("family")
        .filter(invite_filter)
        .distinct()
        .order_by("-created_at", "-id")[:USER_DETAIL_INVITE_LIMIT]
    )

    return {
        "user": _user_row(user),
        "security": {
            "passkeys": {
                "active": active_passkeys.count(),
                "revoked": revoked_passkeys.count(),
                "last_used_at": active_passkeys.aggregate(last=Max("last_used_at"))["last"],
            },
            "sessions": {
                "active": int(getattr(user, "active_sessions", len(active_sessions)) or 0),
                "returned": len(active_sessions),
                "limit": USER_DETAIL_SESSION_LIMIT,
                "results": [
                    {
                        "auth_method": session.auth_method,
                        "client_label": session.client_label,
                        "created_at": session.created_at,
                        "last_seen_at": session.last_seen_at,
                        "last_reauthenticated_at": session.last_reauthenticated_at,
                        "absolute_expires_at": session.absolute_expires_at,
                    }
                    for session in active_sessions
                ],
            },
            "last_successful_login_at": getattr(user, "last_login_at", None),
            "last_successful_auth_method": last_successful_auth_method,
        },
        "invitations": {
            "returned": len(invites),
            "limit": USER_DETAIL_INVITE_LIMIT,
            "results": [
                {
                    "family_id": str(invite.family_id),
                    "family_name": invite.family.name,
                    "role": invite.role,
                    "state": _invite_state(invite, now),
                    "created_at": invite.created_at,
                    "expires_at": invite.expires_at,
                    "accepted_at": invite.accepted_at,
                    "revoked_at": invite.revoked_at,
                }
                for invite in invites
            ],
        },
        "auth_timeline": {
            "returned": len(auth_timeline),
            "limit": USER_DETAIL_AUDIT_LIMIT,
            "results": auth_timeline,
        },
        "privacy": {
            "content_scope": "account_and_operational_metadata_only",
            "excluded": [
                "private_family_content",
                "session_ids_and_refresh_jtis",
                "passkey_credential_ids_and_public_keys",
                "tokens",
                "raw_audit_metadata_and_request_ids",
                "mail_and_notification_content",
                "full_ip_history",
            ],
        },
    }


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_users(request):
    queryset = _users_queryset()
    query = str(request.query_params.get("q") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(email_identities__email__icontains=query)
            | Q(family_memberships__display_name__icontains=query)
            | Q(family_memberships__family__name__icontains=query)
        ).distinct()

    user_status = str(request.query_params.get("status") or "").lower().strip()
    if user_status:
        if user_status not in USER_STATUSES:
            return Response(
                {"detail": "Unsupported user status.", "allowed_statuses": list(USER_STATUSES)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = queryset.filter(is_active=USER_STATUSES[user_status])

    sort_key = str(request.query_params.get("sort") or "username").lower().strip()
    ordering = USER_SORTS.get(sort_key)
    if not ordering:
        return Response(
            {"detail": "Unsupported user sort.", "allowed_sorts": list(USER_SORTS)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    queryset = queryset.order_by(*ordering)

    total = queryset.count()
    limit = _bounded_int(request.query_params.get("limit"), default=100, minimum=1)
    offset = _bounded_int(request.query_params.get("offset"), default=0, minimum=0, maximum=1000000)
    rows = list(queryset[offset : offset + limit])
    return Response(
        {
            "count": total,
            "limit": limit,
            "offset": offset,
            "sort": sort_key,
            "status": user_status or None,
            "results": [_user_row(user) for user in rows],
        }
    )


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_user_detail(request, user_id):
    user = _target_user(user_id)
    if not user:
        return Response({"detail": "Nutzer nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    return Response(_user_detail_payload(user))


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def superadmin_user_email_change(request, user_id):
    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)
    user = _target_user(user_id)
    if not user:
        return Response({"detail": "Nutzer nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    if not user.is_active:
        return Response({"detail": "Für ein deaktiviertes Konto kann keine E-Mail-Änderung gestartet werden."}, status=status.HTTP_409_CONFLICT)
    try:
        with transaction.atomic():
            pending = request_pending_email(user, request.data.get("email") or "")
            queue_verification(pending, locale=_user_locale(user))
    except EmailConflictError as exc:
        return Response({"detail": str(exc), "code": "email_conflict"}, status=status.HTTP_409_CONFLICT)
    except EmailIdentityError as exc:
        return Response({"detail": str(exc), "code": "invalid_email"}, status=status.HTTP_400_BAD_REQUEST)
    try_record_audit_event(
        "superadmin.user.email_change_requested",
        actor=request.user,
        actor_class="superadmin",
        outcome="success",
        reason="admin_action",
        target_type="user",
        target_id=str(user.pk),
    )
    refreshed = _target_user(user.pk)
    return Response({"queued": True, "user": _user_row(refreshed)}, status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def superadmin_user_email_direct(request, user_id):
    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)
    user = _target_user(user_id)
    if not user:
        return Response({"detail": "Nutzer nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    try:
        set_primary_email_direct(user, request.data.get("email") or "")
    except EmailConflictError as exc:
        return Response({"detail": str(exc), "code": "email_conflict"}, status=status.HTTP_409_CONFLICT)
    except EmailIdentityError as exc:
        return Response({"detail": str(exc), "code": "invalid_email"}, status=status.HTTP_400_BAD_REQUEST)
    try_record_audit_event(
        "superadmin.user.email_direct_set",
        actor=request.user,
        actor_class="superadmin",
        outcome="success",
        reason="admin_action",
        target_type="user",
        target_id=str(user.pk),
    )
    refreshed = _target_user(user.pk)
    return Response({"updated": True, "user": _user_row(refreshed)}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def superadmin_user_password_reset(request, user_id):
    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)
    user = _target_user(user_id)
    if not user:
        return Response({"detail": "Nutzer nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    identities = list(user.email_identities.all())
    primary = next((item for item in identities if item.kind == EmailIdentity.Kind.PRIMARY), None)
    if not user.is_active or not primary or not primary.verified_at:
        return Response(
            {"detail": "Passwort-Reset benötigt ein aktives Konto mit bestätigter E-Mail-Adresse.", "code": "password_reset_unavailable"},
            status=status.HTTP_409_CONFLICT,
        )
    queued = request_password_reset(primary.email, locale=_user_locale(user))
    if not queued:
        return Response(
            {"detail": "Der Passwort-Reset wurde nicht erneut eingeplant; möglicherweise gilt noch die Wiederholsperre.", "code": "password_reset_not_queued"},
            status=status.HTTP_409_CONFLICT,
        )
    try_record_audit_event(
        "superadmin.user.password_reset_requested",
        actor=request.user,
        actor_class="superadmin",
        outcome="success",
        reason="admin_action",
        target_type="user",
        target_id=str(user.pk),
    )
    return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def superadmin_user_password_reset_link(request, user_id):
    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)
    user = _target_user(user_id)
    if not user:
        return Response({"detail": "Nutzer nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    reference = create_password_reset_reference(user)
    if not reference:
        return Response(
            {"detail": "Reset-Link benötigt ein aktives Konto mit bestätigter primärer E-Mail-Adresse.", "code": "password_reset_unavailable"},
            status=status.HTTP_409_CONFLICT,
        )
    path = password_reset_path(reference)
    if not path:
        return Response(
            {"detail": "Reset-Link konnte nicht erzeugt werden.", "code": "password_reset_link_failed"},
            status=status.HTTP_409_CONFLICT,
        )
    try_record_audit_event(
        "superadmin.user.password_reset_link_created",
        actor=request.user,
        actor_class="superadmin",
        outcome="success",
        reason="admin_action",
        target_type="user",
        target_id=str(user.pk),
    )
    return Response({"reset_url": _absolute_admin_url(request, path)}, status=status.HTTP_201_CREATED)
