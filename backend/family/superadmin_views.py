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
from entitlements.services import resolve_entitlements

from .invitation_delivery import invitation_delivery_summary
from .invitation_service import issue_invitation
from .models import Family, Membership


RATE_LIMIT_DETAIL = "Zu viele Anfragen. Bitte später erneut versuchen."
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
    entitlement_snapshot = resolve_entitlements(family).as_dict()
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
        "entitlements": entitlement_snapshot,
        "owners": owner_rows,
        "pending_owner_invites": pending_rows,
        "created_at": family.created_at,
        "updated_at": family.updated_at,
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
        rows = rows.order_by(*ordering)
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


@api_view(["PATCH"])
@permission_classes([IsSuperAdmin])
def superadmin_family_detail(request, family_id):
    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)

    family = Family.objects.filter(id=family_id).first()
    if not family:
        return Response({"detail": "Familie nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
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
