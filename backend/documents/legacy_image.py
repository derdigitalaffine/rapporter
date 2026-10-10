"""Compatibility adapter for legacy domains not yet migrated to ``Document``.

This module deliberately contains no domain semantics. Remaining BinaryField
consumers reuse a Documents-owned compatibility boundary while image storage and
OCR keep their historical byte/runtime contract until those rows are migrated to
``Document``. That compatibility matters because legacy domains use normalized
bytes for duplicate hashes and may depend on the existing OCR layout behavior.
"""
from io import BytesIO

from PIL import Image, ImageEnhance, ImageOps, ImageStat, UnidentifiedImageError
import pytesseract

MAX_LEGACY_IMAGE_BYTES = 10 * 1024 * 1024
MAX_LEGACY_IMAGE_PIXELS = 25_000_000
LEGACY_OCR_TIMEOUT_SECONDS = 20
ALLOWED_LEGACY_FORMATS = {"JPEG", "PNG", "WEBP"}


def canonicalize_legacy_image(upload):
    """Preserve the pre-Document image bytes/hash contract for legacy domains.

    PetDocument historically reused Expense receipt normalization: EXIF-aware RGB,
    max 2500px, slight contrast enhancement, then JPEG quality 88. Existing rows
    store the hash of those normalized bytes, so switching this bridge to WebP
    would make identical re-uploads miss duplicate detection. Keep this transform
    here only as an explicit migration compatibility boundary.
    """
    raw = upload.read()
    if not raw:
        raise ValueError("Die Bilddatei ist leer.")
    if len(raw) > MAX_LEGACY_IMAGE_BYTES:
        raise ValueError("Das Dokument darf höchstens 10 MB groß sein.")
    try:
        probe = Image.open(BytesIO(raw))
        image_format = (probe.format or "").upper()
        probe.verify()
        if image_format not in ALLOWED_LEGACY_FORMATS:
            raise ValueError("Nur JPEG-, PNG- oder WebP-Bilder werden unterstützt.")
        image = Image.open(BytesIO(raw))
        width, height = image.size
        if width * height > MAX_LEGACY_IMAGE_PIXELS:
            raise ValueError("Das Bild hat zu viele Bildpunkte.")
        image = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Die Datei ist kein gültiges Bild.") from exc

    warnings = []
    if min(image.size) < 700:
        warnings.append("low_resolution")
    brightness = ImageStat.Stat(ImageOps.grayscale(image)).mean[0]
    if brightness < 55:
        warnings.append("dark")

    image.thumbnail((2500, 2500), Image.Resampling.LANCZOS)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue(), "image/jpeg", warnings


def extract_legacy_image_text(content):
    """Preserve the old PSM-6 OCR behavior behind a Documents-owned adapter.

    This is intentionally *not* the adaptive Document OCR engine: changing a
    legacy PetDocument's extraction behavior is a separate migration scope. The
    only #184 requirement here is to remove the dependency on Expense internals.
    """
    image = Image.open(BytesIO(content))
    image = ImageOps.autocontrast(ImageOps.grayscale(image))
    try:
        return pytesseract.image_to_string(
            image,
            lang="deu+eng",
            config="--psm 6",
            timeout=LEGACY_OCR_TIMEOUT_SECONDS,
        )
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(
            image,
            config="--psm 6",
            timeout=LEGACY_OCR_TIMEOUT_SECONDS,
        )
