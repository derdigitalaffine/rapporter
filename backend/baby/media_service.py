import io
from pathlib import Path

from django.conf import settings
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import PermissionDenied, ValidationError

from .family_modules import care_access, require_module
from .media_models import BabyPrivateMedia

MAX_BYTES = 25 * 1024 * 1024
MAX_IMAGE_DIMENSION = 4096
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_TYPES = {"video/mp4", "video/webm"}


def _root():
    path = Path(settings.MEDIA_ROOT) / "baby-private"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _authorize(user, family, scope):
    require_module(family)
    if scope == BabyPrivateMedia.Scope.PREGNANCY:
        return care_access(user, family, "pregnancy")
    if scope == BabyPrivateMedia.Scope.DEVELOPMENT:
        return care_access(user, family, "development")
    raise ValidationError({"scope": "Use pregnancy or development."})


def _read_limited(upload):
    size = getattr(upload, "size", None)
    if size is not None and size > MAX_BYTES:
        raise ValidationError({"file": "Maximum file size is 25 MB."})
    chunks=[];total=0
    for chunk in upload.chunks():
        total += len(chunk)
        if total > MAX_BYTES:
            raise ValidationError({"file": "Maximum file size is 25 MB."})
        chunks.append(chunk)
    if not total:
        raise ValidationError({"file": "File is empty."})
    return b"".join(chunks)


def _sanitize_image(raw):
    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.verify()
        with Image.open(io.BytesIO(raw)) as source:
            source = ImageOps.exif_transpose(source)
            source.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
            # Rebuild pixel data and save without exif/icc/comment metadata.
            if source.mode not in {"RGB", "RGBA"}:
                source = source.convert("RGBA" if "A" in source.getbands() else "RGB")
            clean = Image.new(source.mode, source.size)
            clean.putdata(list(source.getdata()))
            output = io.BytesIO()
            clean.save(output, format="WEBP", quality=88, method=4)
            return output.getvalue(), "image/webp", ".webp"
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValidationError({"file": "Image could not be processed safely."}) from exc


def save_private_media(*, user, family, upload, scope, pregnancy=None, baby=None):
    _authorize(user, family, scope)
    if scope == BabyPrivateMedia.Scope.PREGNANCY:
        if pregnancy is None or pregnancy.family_id != family.id:
            raise ValidationError({"pregnancy": "Pregnancy does not belong to this family."})
        baby = None
    else:
        if baby is None or baby.family_id != family.id:
            raise ValidationError({"baby": "Baby profile does not belong to this family."})
        pregnancy = None
    raw = _read_limited(upload)
    content_type = (getattr(upload, "content_type", "") or "").lower()
    if content_type in IMAGE_TYPES:
        payload, stored_type, suffix = _sanitize_image(raw)
    elif content_type in VIDEO_TYPES:
        payload, stored_type = raw, content_type
        suffix = ".mp4" if content_type == "video/mp4" else ".webm"
    else:
        raise ValidationError({"file": "Use JPG, PNG, WebP, MP4 or WebM."})

    row = BabyPrivateMedia(
        family=family,
        pregnancy=pregnancy,
        baby=baby,
        scope=scope,
        content_type=stored_type,
        size_bytes=len(payload),
        created_by=user,
    )
    destination = _root() / f"{row.storage_key}{suffix}"
    with transaction.atomic():
        row.save()
        try:
            destination.write_bytes(payload)
        except Exception:
            row.delete()
            raise
    return row


def media_path(row):
    suffix = ".webp" if row.content_type == "image/webp" else ".mp4" if row.content_type == "video/mp4" else ".webm"
    path = _root() / f"{row.storage_key}{suffix}"
    if not path.exists() or not path.is_file():
        raise ValidationError({"media": "Stored file is unavailable."})
    return path


def get_private_media_for_user(*, user, media_id):
    row = BabyPrivateMedia.objects.select_related("family", "pregnancy", "baby").filter(pk=media_id).first()
    if not row:
        raise ValidationError({"media": "Media not found."})
    _authorize(user, row.family, row.scope)
    return row, media_path(row)


def delete_private_media(*, user, media_id):
    row, path = get_private_media_for_user(user=user, media_id=media_id)
    if row.created_by_id != user.id:
        _, access = _authorize(user, row.family, row.scope)
        if not access.is_guardian:
            raise PermissionDenied("Only the uploader or a guardian can delete this media.")
    row.delete()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
