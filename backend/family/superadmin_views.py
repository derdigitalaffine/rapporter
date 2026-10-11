from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth_abuse.service import enforce
from auth_identity.models import EmailIdentity
from auth_identity.service import EmailIdentityError, normalize_email
from auth_sessions.service import require_fresh_session
from entitlements.services import resolve_entitlements, resolve_entitlements_for_families
from telemetry.models import AuditEvent, UsageEvent

from .invitation_delivery import invitation_delivery_summary, prime_invitation_delivery_summaries
from .invitation_service import issue_invitation
from .models import Family, IntegrationSource, Membership


RATE_LIMIT_DETAIL = "Zu viele Anfragen. Bitte später erneut versuchen."
FAMILY_DETAIL_AUDIT_LIMIT = 30
FAMILY_DETAIL_INVITE_LIMIT = 50
FAMILY_SORTS = {
    "name": ("name", "created_at"),
    "-name": ("-name", "created_at"),
    "created_at": ("created_at", "id"),
    "-created_at": ("-created_at", "id"),
    "last_activity": ("last_activity_at", "id"),
    "-last_activity": ("-last_activity_at", "id"),
    "members": ("member_count", "id"),
    "-members": ("-member_count", "id"),
}
FAMILY_STATUSES = {Family.Status.ACTIVE, Family.Status.SUSPENDED}


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


def _rate_limited_response(decision):
    response = Response(
        {
            "detail": RATE_LIMIT_DETAIL,
            "code": "rate_limited",
            "retry_after": decision.retry_after,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(decision.retry_after)
    return response


def _enforce_sensitive_action(request):
    require_fresh_session(request)
    return enforce("superadmin.sensitive_action", request=request, user=request.user)


def _normalized_required_email(value):
    try:
        return normalize_email(value)
    except EmailIdentityError:
        return ""


def _primary_identity(user):
    return next(
        (identity for identity in user.email_identities.all() if identity.kind == EmailIdentity.Kind.PRIMARY),
        None,
    )


def _families_queryset():
    now = timezone.now()
    return (
        Family.objects.prefetch_related(
            "memberships__user__email_identities",
            "invitations",
        )
        .annotate(
            member_count=Count("memberships", distinct=True),
            owner_count=Count(
                "memberships",
                filter=Q(memberships__role=Membership.Role.OWNER),
                distinct=True,
            ),
            verified_owner_count=Count(
                "memberships",
                filter=Q(
                    memberships__role=Membership.Role.OWNER,
                    memberships__user__email_identities__kind=EmailIdentity.Kind.PRIMARY,
                    memberships__user__email_identities__verified_at__isnull=False,
                ),
                distinct=True,
            ),
            pending_invite_count=Count(
                "invitations",
                filter=Q(
                    invitations__accepted_at__isnull=True,
                    invitations__revoked_at__isnull=True,
                    invitations__expires_at__gt=now,
                ),
                distinct=True,
            ),
            last_activity_at=Max("usage_events__occurred_at"),
        )
    )


def _prime_family_rows(families):
    family_list = list(families)
    if not family_list:
        return family_list
    snapshots = resolve_entitlements_for_families(family_list)
    now = timezone.now()
    pending_invites = []
    for family in family_list:
        family._superadmin_entitlement_snapshot = snapshots[family.pk]
        pending_invites.extend(
            invite
            for invite in family.invitations.all()
            if invite.accepted_at is None and invite.revoked_at is None and invite.expires_at > now
        )
    prime_invitation_delivery_summaries(pending_invites)
    return family_list


def _family_row(family):
    now = timezone.now()
    memberships = list(family.memberships.all())
    owners = [item for item in memberships if item.role == Membership.Role.OWNER]
    pending = [
        item
        for item in family.invitations.all()
        if item.accepted_at is None and item.revoked_at is None and item.expires_at > now
    ]
    pending.sort(key=lambda item: item.created_at, reverse=True)
    pending_rows = []
    for item in pending:
        delivery = invitation_delivery_summary(item)
        pending_rows.append(
            {
                "id": str(item.id),
                "email": item.email,
                "display_name": item.display_name,
                "expires_at": item.expires_at,
                "delivery_status": delivery["delivery_status"],
                "last_sent_at": delivery["last_sent_at"],
            }
        )
    owner_rows = []
    for item in owners:
        primary = _primary_identity(item.user)
        owner_rows.append(
            {
                "username": item.user.username,
                "email": primary.email if primary else item.user.email,
                "display_name": item.display_name,
                "email_verified": bool(primary and primary.verified_at),
            }
        )
    entitlement_snapshot = getattr(family, "_superadmin_entitlement_snapshot", None)
    if entitlement_snapshot is None:
        entitlement_snapshot = resolve_entitlements(family)
    return {
        "id": str(family.id),
        "name": family.name,
        "slug": family.slug,
        "locale": family.locale,
        "timezone": family.timezone,
        "status": family.status,
        "member_count": int(getattr(family, "member_count", len(memberships)) or 0),
        "owner_count": int(getattr(family, "owner_count", len(owners)) or 0),
        "verified_owner_count": int(
            getattr(family, "verified_owner_count", sum(1 for row in owner_rows if row["email_verified"])) or 0
        ),
        "pending_invite_count": int(getattr(family, "pending_invite_count", len(pending)) or 0),
        "last_activity_at": getattr(family, "last_activity_at", None),
        "entitlements": entitlement_snapshot.as_dict(),
        "owners": owner_rows,
        "pending_owner_invites": pending_rows,
        "created_at": family.created_at,
        "updated_at": family.updated_at,
    }


def _membership_rows(family):
    rows = []
    for membership in family.memberships.all():
        primary = _primary_identity(membership.user)
        rows.append(
            {
                "id": str(membership.id),
                "user_id": membership.user_id,
                "username": membership.user.username,
                "display_name": membership.display_name,
                "role": membership.role,
                "account_active": membership.user.is_active,
                "email": primary.email if primary else membership.user.email,
                "email_verified": bool(primary and primary.verified_at),
            }
        )
    rows.sort(key=lambda row: (row["role"] != Membership.Role.OWNER, (row["display_name"] or row["username"]).casefold(), row["id"]))
    return rows


def _invite_state(invite, now):
    if invite.accepted_at is not None:
        return "accepted"
    if invite.revoked_at is not None:
        return "revoked"
    if invite.expires_at <= now:
        return "expired"
    return "pending"


def _family_detail_payload(family):
    now = timezone.now()
    activity = UsageEvent.objects.filter(family=family, event_key="activity.foreground")
    modules = list(
        UsageEvent.objects.filter(
            family=family,
            event_key="module.used",
            occurred_at__gte=now - timedelta(days=30),
        )
        .values("dimension_key")
        .annotate(active_users=Count("user_id", distinct=True), last_used_at=Max("occurred_at"))
        .order_by("dimension_key")
    )
    integration_rows = IntegrationSource.objects.filter(family=family)
    integration_enabled = integration_rows.filter(enabled=True)
    integration_degraded = integration_enabled.filter(Q(consecutive_failures__gt=0) | Q(last_sync_status="failed"))
    latest_integration_success = integration_enabled.aggregate(last=Max("last_success_at"))["last"]

    invite_rows = []
    invites = sorted(list(family.invitations.all()), key=lambda item: (item.created_at, str(item.id)), reverse=True)
    for invite in invites[:FAMILY_DETAIL_INVITE_LIMIT]:
        invite_rows.append(
            {
                "id": str(invite.id),
                "role": invite.role,
                "email": invite.email,
                "display_name": invite.display_name,
                "state": _invite_state(invite, now),
                "created_at": invite.created_at,
                "expires_at": invite.expires_at,
                "accepted_at": invite.accepted_at,
                "revoked_at": invite.revoked_at,
            }
        )

    audit_rows = list(
        AuditEvent.objects.filter(family=family, actor_class=AuditEvent.ActorClass.SUPERADMIN)
        .order_by("-occurred_at", "-id")
        .values("occurred_at", "event_key", "outcome", "reason", "target_type")[:FAMILY_DETAIL_AUDIT_LIMIT]
    )

    return {
        "family": _family_row(family),
        "memberships": _membership_rows(family),
        "activity": {
            "active_users_7d": activity.filter(occurred_at__gte=now - timedelta(days=7)).values("user_id").distinct().count(),
            "active_users_30d": activity.filter(occurred_at__gte=now - timedelta(days=30)).values("user_id").distinct().count(),
            "last_activity_at": activity.aggregate(last=Max("occurred_at"))["last"],
            "module_adoption_30d": modules,
        },
        "invitations": {
            "total": len(invites),
            "returned": len(invite_rows),
            "limit": FAMILY_DETAIL_INVITE_LIMIT,
            "results": invite_rows,
        },
        "integrations": {
            "enabled": integration_enabled.count(),
            "degraded": integration_degraded.count(),
            "latest_success_at": latest_integration_success,
        },
        "superadmin_audit": {
            "limit": FAMILY_DETAIL_AUDIT_LIMIT,
            "results": audit_rows,
        },
        "privacy": {
            "content_scope": "administrative_metadata_only",
            "excluded": [
                "family_content",
                "integration_config",
                "integration_endpoints",
                "raw_audit_metadata",
                "tokens",
                "credential_material",
            ],
        },
    }


def _unique_slug(name):
    base = slugify(name)[:100] or "family"
    slug = base
    counter = 2
    while Family.objects.filter(slug=slug).exists():
        suffix = f"-{counter}"
        slug = f"{base[:120-len(suffix)]}{suffix}"
        counter += 1
    return slug


@api_view(["GET", "POST"])
@permission_classes([IsSuperAdmin])
def superadmin_families(request):
    if request.method == "GET":
        rows = _families_queryset()
        query = str(request.query_params.get("q") or "").strip()
        if query:
            rows = rows.filter(
                Q(name__icontains=query)
                | Q(slug__icontains=query)
                | Q(memberships__display_name__icontains=query)
                | Q(memberships__user__username__icontains=query)
                | Q(memberships__user__email__icontains=query)
                | Q(memberships__user__email_identities__email__icontains=query)
            ).distinct()

        family_status = str(request.query_params.get("status") or "").strip().lower()
        if family_status:
            if family_status not in FAMILY_STATUSES:
                return Response(
                    {"detail": "Unsupported family status.", "allowed_statuses": sorted(FAMILY_STATUSES)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            rows = rows.filter(status=family_status)

        sort_key = str(request.query_params.get("sort") or "name").strip().lower()
        ordering = FAMILY_SORTS.get(sort_key)
        if not ordering:
            return Response(
                {"detail": "Unsupported family sort.", "allowed_sorts": list(FAMILY_SORTS)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        rows = _prime_family_rows(rows.order_by(*ordering))
        return Response([_family_row(family) for family in rows])

    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)

    name = str(request.data.get("name") or "").strip()
    owner_email = _normalized_required_email(request.data.get("owner_email") or "")
    owner_name = str(request.data.get("owner_name") or "").strip()
    locale = str(request.data.get("locale") or "de").strip().lower()
    family_timezone = str(request.data.get("timezone") or "Europe/Berlin").strip()
    if not name:
        return Response({"detail": "Familienname fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    if not owner_email:
        return Response({"detail": "Gültige Owner-E-Mail fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    if locale not in {"de", "en"}:
        locale = "de"

    with transaction.atomic():
        family = Family.objects.create(
            name=name,
            slug=_unique_slug(name),
            locale=locale,
            timezone=family_timezone,
            status=Family.Status.ACTIVE,
        )
        invite, _token = issue_invitation(
            family=family,
            role=Membership.Role.OWNER,
            invited_by=request.user,
            email=owner_email,
            display_name=owner_name,
            expires_at=timezone.now() + timedelta(days=7),
        )
    return Response(
        {
            "family": _family_row(family),
            "invite_id": str(invite.id),
            "delivery": invitation_delivery_summary(invite)["delivery_status"],
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH"])
@permission_classes([IsSuperAdmin])
def superadmin_family_detail(request, family_id):
    if request.method == "PATCH":
        decision = _enforce_sensitive_action(request)
        if not decision.allowed:
            return _rate_limited_response(decision)

    family = _families_queryset().filter(id=family_id).first()
    if not family:
        return Response({"detail": "Familie nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        _prime_family_rows([family])
        return Response(_family_detail_payload(family))

    requested = request.data.get("status")
    if requested not in Family.Status.values:
        return Response({"detail": "Ungültiger Familienstatus."}, status=status.HTTP_400_BAD_REQUEST)
    family.status = requested
    family.save(update_fields=["status", "updated_at"])
    return Response(_family_row(family))


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def superadmin_owner_invite(request, family_id):
    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)

    family = Family.objects.filter(id=family_id).first()
    if not family:
        return Response({"detail": "Familie nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    if family.status != Family.Status.ACTIVE:
        return Response({"detail": "Eine gesperrte Familie kann keine neue Owner-Einladung erhalten."}, status=status.HTTP_409_CONFLICT)
    email = _normalized_required_email(request.data.get("email") or "")
    display_name = str(request.data.get("display_name") or "").strip()
    if not email:
        return Response({"detail": "Gültige Owner-E-Mail fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    invite, _token = issue_invitation(
        family=family,
        role=Membership.Role.OWNER,
        invited_by=request.user,
        email=email,
        display_name=display_name,
        expires_at=timezone.now() + timedelta(days=7),
    )
    return Response(
        {
            "invite_id": str(invite.id),
            "delivery": invitation_delivery_summary(invite)["delivery_status"],
            "family": _family_row(family),
        },
        status=status.HTTP_201_CREATED,
    )
