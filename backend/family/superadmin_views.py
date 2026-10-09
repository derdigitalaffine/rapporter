from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Family, FamilyInvitation, Membership


class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


def _family_row(family):
    owners = family.memberships.filter(role=Membership.Role.OWNER).select_related("user")
    pending = family.invitations.filter(
        role=Membership.Role.OWNER,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at")
    return {
        "id": str(family.id),
        "name": family.name,
        "slug": family.slug,
        "locale": family.locale,
        "timezone": family.timezone,
        "status": family.status,
        "member_count": family.memberships.count(),
        "owners": [
            {"username": item.user.username, "email": item.user.email, "display_name": item.display_name}
            for item in owners
        ],
        "pending_owner_invites": [
            {"token": item.token, "email": item.email, "display_name": item.display_name, "expires_at": item.expires_at}
            for item in pending
        ],
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
        rows = Family.objects.prefetch_related("memberships__user", "invitations").order_by("name", "created_at")
        return Response([_family_row(family) for family in rows])

    name = str(request.data.get("name") or "").strip()
    owner_email = str(request.data.get("owner_email") or "").strip().lower()
    owner_name = str(request.data.get("owner_name") or "").strip()
    locale = str(request.data.get("locale") or "de").strip().lower()
    family_timezone = str(request.data.get("timezone") or "Europe/Berlin").strip()
    if not name:
        return Response({"detail": "Familienname fehlt."}, status=status.HTTP_400_BAD_REQUEST)
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
        invite = FamilyInvitation.objects.create(
            family=family,
            role=Membership.Role.OWNER,
            invited_by=request.user,
            email=owner_email,
            display_name=owner_name,
            expires_at=timezone.now() + timedelta(days=7),
        )
    return Response({"family": _family_row(family), "invite_token": invite.token}, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsSuperAdmin])
def superadmin_family_detail(request, family_id):
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
    family = Family.objects.filter(id=family_id).first()
    if not family:
        return Response({"detail": "Familie nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    if family.status != Family.Status.ACTIVE:
        return Response({"detail": "Eine gesperrte Familie kann keine neue Owner-Einladung erhalten."}, status=status.HTTP_409_CONFLICT)
    email = str(request.data.get("email") or "").strip().lower()
    display_name = str(request.data.get("display_name") or "").strip()
    invite = FamilyInvitation.objects.create(
        family=family,
        role=Membership.Role.OWNER,
        invited_by=request.user,
        email=email,
        display_name=display_name,
        expires_at=timezone.now() + timedelta(days=7),
    )
    return Response({"invite_token": invite.token, "family": _family_row(family)}, status=status.HTTP_201_CREATED)
