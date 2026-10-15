from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .avatar_appearance import avatar_color, avatar_mode, deterministic_avatar_color
from .models import Family, Membership, UserProfile


def _avatar_payload(member, profile):
    if not profile:
        return {
            "avatar": member.avatar or "",
            "avatar_url": member.avatar or "",
            "avatar_mode": "initials",
            "avatar_icon_key": "",
            "avatar_color": deterministic_avatar_color(member.user_id),
        }
    url = (
        f"/api/profile/avatar/{member.user_id}/128/?v={profile.avatar_version}"
        if profile.avatar_key
        else ""
    )
    return {
        "avatar": url or member.avatar or "",
        "avatar_url": url,
        "avatar_mode": avatar_mode(profile),
        "avatar_icon_key": profile.avatar_icon_key or "",
        "avatar_color": avatar_color(profile),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_audience_options(request):
    family = Family.objects.filter(
        id=request.query_params.get("family"),
        status=Family.Status.ACTIVE,
        memberships__user=request.user,
    ).first()
    if not family:
        return Response({"detail": "Familie nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)

    members = list(
        Membership.objects.filter(family=family)
        .select_related("user")
        .order_by("created_at")
    )
    profiles = {
        profile.user_id: profile
        for profile in UserProfile.objects.filter(user_id__in=[member.user_id for member in members])
    }
    return Response(
        {
            "groups": [
                {"id": "family", "label": "Ganze Familie"},
                {"id": "adults", "label": "Erwachsene"},
                {"id": "children", "label": "Kinder & Jugendliche"},
            ],
            "members": [
                {
                    "id": str(member.id),
                    "user_id": member.user_id,
                    "name": member.display_name or member.user.get_short_name() or member.user.username,
                    "display_name": member.display_name or member.user.get_short_name() or member.user.username,
                    "username": member.user.username,
                    "role": member.role,
                    **_avatar_payload(member, profiles.get(member.user_id)),
                }
                for member in members
            ],
        }
    )
