from django.http import Http404
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from family.avatar_appearance import appearance_payload
from family.membership_calendar import CALENDAR_COLOR_PALETTE, get_calendar_color
from family.models import Family, Membership
from family.profile_views import (
    _avatar_edit_url,
    _avatar_file_response,
    _avatar_master_path,
    _avatar_path,
    _avatar_url,
    _profile,
    _remove_avatar,
    _store_avatar,
    _update_appearance,
)

from .child_identity_service import require_child_membership_guardian


def _managed_child_membership(request_user, membership_id):
    target = (
        Membership.objects.filter(pk=membership_id, family__status=Family.Status.ACTIVE)
        .select_related("family", "user")
        .first()
    )
    if not target or target.role != Membership.Role.CHILD:
        raise PermissionDenied("Kinderprofil ist nicht verfügbar.")
    if target.user_id == request_user.id:
        return target
    actor = Membership.objects.filter(family=target.family, user=request_user).first()
    if not actor:
        raise PermissionDenied("Kinderprofil ist nicht verfügbar.")
    if actor.role == Membership.Role.OWNER:
        return target
    require_child_membership_guardian(request_user, target, manage=True)
    return target


def _appearance_payload(profile, membership):
    return {
        "membership_id": str(membership.id),
        "avatar_url": _avatar_url(profile),
        "avatar_edit_url": f"/api/baby/memberships/{membership.id}/avatar/source/" if profile.avatar_key else "",
        **appearance_payload(profile),
        "calendar_color": get_calendar_color(membership),
        "calendar_color_palette": list(CALENDAR_COLOR_PALETTE),
    }


@api_view(["GET", "POST", "PATCH", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def managed_child_avatar(request, membership_id):
    membership = _managed_child_membership(request.user, membership_id)
    profile = _profile(membership.user)
    if request.method == "GET":
        return Response(_appearance_payload(profile, membership))
    if request.method == "DELETE":
        _remove_avatar(profile)
        return Response(_appearance_payload(profile, membership))
    if request.method == "PATCH":
        try:
            _update_appearance(profile, request.data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_appearance_payload(profile, membership))

    upload = request.FILES.get("avatar")
    if not upload:
        return Response({"detail": "Profilbild fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        _store_avatar(profile, upload, request.FILES.get("avatar_source"))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except OSError:
        return Response({"detail": "Profilbild konnte nicht gespeichert werden."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(_appearance_payload(profile, membership))


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def managed_child_avatar_source(request, membership_id):
    membership = _managed_child_membership(request.user, membership_id)
    profile = _profile(membership.user)
    if not profile.avatar_key:
        raise Http404()
    path = _avatar_master_path(profile.avatar_key)
    if not path.is_file():
        path = _avatar_path(profile.avatar_key, 256)
    if not path.is_file():
        raise Http404()
    return _avatar_file_response(path, profile, "source")
