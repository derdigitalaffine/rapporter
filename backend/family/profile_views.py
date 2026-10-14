import io
import uuid
from datetime import date
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404
from PIL import Image
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .birthday_age import age_is_enabled, set_age_enabled
from .membership_calendar import CALENDAR_COLOR_PALETTE, get_calendar_color, normalize_calendar_color, set_calendar_color
from .models import Family, Membership, UserProfile


AVATAR_SIZES = (64, 128, 256)
AVATAR_MASTER_MAX_DIMENSION = 2048


def _profile(user):
    return UserProfile.objects.get_or_create(user=user)[0]


def _membership(user, family_id=None):
    rows = Membership.objects.filter(user=user, family__status=Family.Status.ACTIVE).select_related("family")
    if family_id:
        member = rows.filter(family_id=family_id).first()
        if not member:
            raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
        return member
    return rows.first()


def _avatar_url(profile, size=256):
    if not profile.avatar_key:
        return ""
    return f"/api/profile/avatar/{profile.user_id}/{size}/?v={profile.avatar_version}"


def _avatar_edit_url(profile):
    if not profile.avatar_key:
        return ""
    return f"/api/profile/avatar/{profile.user_id}/source/?v={profile.avatar_version}"


def _payload(profile, membership):
    return {
        "user_id": profile.user_id,
        "username": profile.user.username,
        "email": profile.user.email or "",
        "avatar_url": _avatar_url(profile),
        "avatar_edit_url": _avatar_edit_url(profile),
        "birth_month": profile.birth_month,
        "birth_day": profile.birth_day,
        "birth_year": profile.birth_year,
        "family": str(membership.family_id) if membership else None,
        "membership_id": str(membership.id) if membership else None,
        "display_name": (membership.display_name if membership else "") or profile.user.get_short_name() or profile.user.username,
        "role": membership.role if membership else None,
        "birthday_visibility": membership.birthday_visibility if membership else Membership.BirthdayVisibility.HIDDEN,
        "show_birthday_age": age_is_enabled(membership.family, f"member:{membership.id}") if membership else True,
        "calendar_color": get_calendar_color(membership) if membership else None,
        "calendar_color_palette": list(CALENDAR_COLOR_PALETTE),
    }


def _validated_birthday(profile, data):
    month = data.get("birth_month", profile.birth_month)
    day = data.get("birth_day", profile.birth_day)
    year = data.get("birth_year", profile.birth_year)
    month = None if month in (None, "") else int(month)
    day = None if day in (None, "") else int(day)
    year = None if year in (None, "") else int(year)
    if month is None and day is None and year is None:
        return None, None, None
    if month is None or day is None:
        raise ValueError("Tag und Monat müssen gemeinsam angegeben werden.")
    if year is not None and not 1900 <= year <= date.today().year:
        raise ValueError("Geburtsjahr ist außerhalb des gültigen Bereichs.")
    try:
        date(year or 2000, month, day)
    except ValueError as exc:
        raise ValueError("Geburtstag ist kein gültiges Kalenderdatum.") from exc
    return month, day, year


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def profile_detail(request):
    profile = _profile(request.user)
    family_id = request.query_params.get("family") or request.data.get("family")
    membership = _membership(request.user, family_id)
    if request.method == "PATCH":
        try:
            month, day, year = _validated_birthday(profile, request.data)
        except (TypeError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        visibility = request.data.get("birthday_visibility", membership.birthday_visibility if membership else Membership.BirthdayVisibility.HIDDEN)
        if visibility not in Membership.BirthdayVisibility.values:
            return Response({"detail": "Ungültige Geburtstagssichtbarkeit."}, status=status.HTTP_400_BAD_REQUEST)
        show_age = request.data.get("show_birthday_age", None)
        if show_age is not None and not isinstance(show_age, bool):
            return Response({"detail": "Ungültige Altersanzeige-Einstellung."}, status=status.HTTP_400_BAD_REQUEST)
        calendar_color = None
        if membership and "calendar_color" in request.data:
            try:
                calendar_color = normalize_calendar_color(request.data.get("calendar_color"))
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            profile.birth_month = month
            profile.birth_day = day
            profile.birth_year = year
            profile.save(update_fields=["birth_month", "birth_day", "birth_year", "updated_at"])
            if membership:
                if "display_name" in request.data:
                    membership.display_name = str(request.data.get("display_name") or "").strip()[:80]
                membership.birthday_visibility = visibility
                membership.save(update_fields=["display_name", "birthday_visibility", "updated_at"])
                if show_age is not None:
                    set_age_enabled(membership.family, f"member:{membership.id}", show_age)
                if calendar_color is not None:
                    set_calendar_color(membership, calendar_color)
    return Response(_payload(profile, membership))


def _avatar_directory():
    directory = Path(settings.MEDIA_ROOT) / "avatars"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _avatar_path(key, size):
    return _avatar_directory() / f"{key}-{size}.webp"


def _avatar_master_path(key):
    return _avatar_directory() / f"{key}-source.webp"


def _delete_avatar_files(key):
    if not key:
        return
    for path in [*(_avatar_path(key, size) for size in AVATAR_SIZES), _avatar_master_path(key)]:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _decode_image_upload(upload):
    from documents.images import decode_image, read_image_upload
    return decode_image(read_image_upload(upload))


def _decode_avatar(upload):
    image = _decode_image_upload(upload)
    side = min(image.width, image.height)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def _decode_avatar_source(upload):
    image = _decode_image_upload(upload)
    image.thumbnail((AVATAR_MASTER_MAX_DIMENSION, AVATAR_MASTER_MAX_DIMENSION), Image.Resampling.LANCZOS)
    return image


def _save_avatar_master(image, key):
    image.save(_avatar_master_path(key), format="WEBP", quality=90, method=6)


@api_view(["POST", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def profile_avatar(request):
    profile = _profile(request.user)
    if request.method == "DELETE":
        old_key = profile.avatar_key
        profile.avatar_key = ""
        profile.avatar_version = uuid.uuid4()
        profile.save(update_fields=["avatar_key", "avatar_version", "updated_at"])
        _delete_avatar_files(old_key)
        return Response(_payload(profile, _membership(request.user, request.query_params.get("family"))))
    upload = request.FILES.get("avatar")
    if not upload:
        return Response({"detail": "Profilbild fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    source_upload = request.FILES.get("avatar_source")
    try:
        image = _decode_avatar(upload)
        source_image = _decode_avatar_source(source_upload) if source_upload else image.copy()
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    key = uuid.uuid4().hex
    try:
        _save_avatar_master(source_image, key)
        for size in AVATAR_SIZES:
            rendition = image.resize((size, size), Image.Resampling.LANCZOS)
            rendition.save(_avatar_path(key, size), format="WEBP", quality=88, method=6)
    except OSError:
        _delete_avatar_files(key)
        return Response({"detail": "Profilbild konnte nicht gespeichert werden."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    old_key = profile.avatar_key
    profile.avatar_key = key
    profile.avatar_version = uuid.uuid4()
    profile.save(update_fields=["avatar_key", "avatar_version", "updated_at"])
    _delete_avatar_files(old_key)
    return Response(_payload(profile, _membership(request.user, request.query_params.get("family"))))


def _can_read_avatar(request_user, target_user_id):
    if request_user.is_superuser or request_user.id == target_user_id:
        return True
    return Membership.objects.filter(
        user=request_user,
        family__status=Family.Status.ACTIVE,
        family__memberships__user_id=target_user_id,
    ).exists()


def _avatar_file_response(path, profile, variant):
    response = FileResponse(path.open("rb"), content_type="image/webp")
    response["Cache-Control"] = "private, max-age=31536000, immutable"
    response["ETag"] = f'"{profile.avatar_version}-{variant}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def profile_avatar_file(request, user_id, size):
    if size not in AVATAR_SIZES or not _can_read_avatar(request.user, user_id):
        raise Http404()
    profile = UserProfile.objects.filter(user_id=user_id).first()
    if not profile or not profile.avatar_key:
        raise Http404()
    path = _avatar_path(profile.avatar_key, size)
    if not path.is_file():
        raise Http404()
    return _avatar_file_response(path, profile, size)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def profile_avatar_source(request, user_id):
    # The source can contain pixels outside the visible crop and is therefore
    # deliberately stricter than the family-readable avatar renditions.
    if not (request.user.is_superuser or request.user.id == user_id):
        raise Http404()
    profile = UserProfile.objects.filter(user_id=user_id).first()
    if not profile or not profile.avatar_key:
        raise Http404()
    path = _avatar_master_path(profile.avatar_key)
    if not path.is_file():
        # Avatars created before source retention remain editable, but only inside
        # the previously saved square. New uploads retain the larger master.
        path = _avatar_path(profile.avatar_key, 256)
    if not path.is_file():
        raise Http404()
    return _avatar_file_response(path, profile, "source")