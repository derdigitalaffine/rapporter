import uuid

from PIL import Image
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from family.membership_calendar import CALENDAR_COLOR_PALETTE, get_calendar_color
from family.models import Family, Membership
from family.profile_views import AVATAR_SIZES, _avatar_path, _avatar_url, _decode_avatar, _delete_avatar_files, _profile


def _managed_child_membership(request_user, membership_id):
    target = (
        Membership.objects.filter(pk=membership_id, family__status=Family.Status.ACTIVE)
        .select_related('family', 'user')
        .first()
    )
    if not target:
        raise PermissionDenied('Kinderprofil ist nicht verfügbar.')
    actor = Membership.objects.filter(family=target.family, user=request_user).first()
    if not actor or actor.role not in {Membership.Role.OWNER, Membership.Role.ADULT}:
        raise PermissionDenied('Nur Owner/Erwachsene können Kinderprofile gestalten.')
    if target.role != Membership.Role.CHILD:
        raise PermissionDenied('Nur Kinderprofile können hier gestaltet werden.')
    return target


def _appearance_payload(profile, membership):
    return {
        'membership_id': str(membership.id),
        'avatar_url': _avatar_url(profile),
        'calendar_color': get_calendar_color(membership),
        'calendar_color_palette': list(CALENDAR_COLOR_PALETTE),
    }


def _store_avatar(profile, upload):
    image = _decode_avatar(upload)
    key = uuid.uuid4().hex
    try:
        for size in AVATAR_SIZES:
            rendition = image.resize((size, size), Image.Resampling.LANCZOS)
            rendition.save(_avatar_path(key, size), format='WEBP', quality=88, method=6)
    except OSError:
        _delete_avatar_files(key)
        raise
    old_key = profile.avatar_key
    profile.avatar_key = key
    profile.avatar_version = uuid.uuid4()
    profile.save(update_fields=['avatar_key', 'avatar_version', 'updated_at'])
    _delete_avatar_files(old_key)


def _remove_avatar(profile):
    old_key = profile.avatar_key
    profile.avatar_key = ''
    profile.avatar_version = uuid.uuid4()
    profile.save(update_fields=['avatar_key', 'avatar_version', 'updated_at'])
    _delete_avatar_files(old_key)


@api_view(['POST', 'DELETE'])
@permission_classes([permissions.IsAuthenticated])
def managed_child_avatar(request, membership_id):
    membership = _managed_child_membership(request.user, membership_id)
    profile = _profile(membership.user)
    if request.method == 'DELETE':
        _remove_avatar(profile)
        return Response(_appearance_payload(profile, membership))

    upload = request.FILES.get('avatar')
    if not upload:
        return Response({'detail': 'Profilbild fehlt.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        _store_avatar(profile, upload)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except OSError:
        return Response({'detail': 'Profilbild konnte nicht gespeichert werden.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response(_appearance_payload(profile, membership))