import io
import uuid
import warnings
from datetime import date
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Family, Membership, UserProfile


AVATAR_SIZES = (64, 128, 256)
MAX_AVATAR_BYTES = 10 * 1024 * 1024
MAX_AVATAR_PIXELS = 20_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


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


def _payload(profile, membership):
    return {
        "user_id": profile.user_id,
        "username": profile.user.username,
        "email": profile.user.email or "",
        "avatar_url": _avatar_url(profile),
        "birth_month": profile.birth_month,
        "birth_day": profile.birth_day,
        "birth_year": profile.birth_year,
        "family": str(membership.family_id) if membership else None,
        "membership_id": str(membership.id) if membership else None,
        "display_name": (membership.display_name if membership else "") or profile.user.get_short_name() or profile.user.username,
        "role": membership.role if membership else None,
        "birthday_visibility": membership.birthday_visibility if membership else Membership.BirthdayVisibility.HIDDEN,
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
    return Response(_payload(profile, membership))


def _avatar_directory():
    directory = Path(settings.MEDIA_ROOT) / "avatars"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _avatar_path(key, size):
    return _avatar_directory() / f"{key}-{size}.webp"


def _delete_avatar_files(key):
    if not key:
        return
    for size in AVATAR_SIZES:
        try:
            _avatar_path(key, size).unlink(missing_ok=True)
        except OSError:
            pass


def _decode_avatar(upload):
    if upload.size > MAX_AVATAR_BYTES:
        raise ValueError("Profilbild darf maximal 10 MB groß sein.")
    raw = upload.read(MAX_AVATAR_BYTES + 1)
    if len(raw) > MAX_AVATAR_BYTES:
        raise ValueError("Profilbild darf maximal 10 MB groß sein.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                if probe.format not in ALLOWED_FORMATS:
                    raise ValueError("Nur JPEG, PNG oder WebP sind erlaubt.")
                if probe.width * probe.height > MAX_AVATAR_PIXELS:
                    raise ValueError("Profilbild hat zu viele Pixel.")
                probe.verify()
            with Image.open(io.BytesIO(raw)) as decoded:
                image = ImageOps.exif_transpose(decoded)
                image.load()
                if image.width * image.height > MAX_AVATAR_PIXELS:
                    raise ValueError("Profilbild hat zu viele Pixel.")
                mode = "RGBA" if "A" in image.getbands() else "RGB"
                image = image.convert(mode)
                side = min(image.width, image.height)
                left = (image.width - side) // 2
                top = (image.height - side) // 2
                return image.crop((left, top, left + side, top + side))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Datei ist kein gültiges, sicheres Bild.") from exc


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
    try:
        image = _decode_avatar(upload)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    key = uuid.uuid4().hex
    try:
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
    response = FileResponse(path.open("rb"), content_type="image/webp")
    response["Cache-Control"] = "private, max-age=31536000, immutable"
    response["ETag"] = f'"{profile.avatar_version}-{size}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
