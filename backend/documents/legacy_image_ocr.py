"""Compatibility helpers for legacy private image-backed domain documents.

These helpers keep generic image normalization/OCR in the Documents domain while
older domains migrate their persistence to the durable Document Processing Core.
They intentionally expose no receipt parsing or domain semantics.
"""
import io

from PIL import Image, ImageEnhance, ImageOps, ImageStat, UnidentifiedImageError
import pytesseract

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
OCR_TIMEOUT_SECONDS = 20
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def normalize_image_upload(upload):
    raw = upload.read()
    if not raw:
        raise ValueError("Die Bilddatei ist leer.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Der Beleg darf höchstens 10 MB groß sein.")
    try:
        probe = Image.open(io.BytesIO(raw))
        image_format = (probe.format or "").upper()
        probe.verify()
        if image_format not in ALLOWED_FORMATS:
            raise ValueError("Nur JPEG-, PNG- oder WebP-Belege werden unterstützt.")
        image = Image.open(io.BytesIO(raw))
        width, height = image.size
        if width * height > MAX_IMAGE_PIXELS:
            raise ValueError("Der Beleg hat zu viele Bildpunkte.")
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
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue(), "image/jpeg", warnings


def ocr_image_content(content):
    image = Image.open(io.BytesIO(content))
    image = ImageOps.autocontrast(ImageOps.grayscale(image))
    try:
        return pytesseract.image_to_string(
            image,
            lang="deu+eng",
            config="--psm 6",
            timeout=OCR_TIMEOUT_SECONDS,
        )
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(
            image,
            config="--psm 6",
            timeout=OCR_TIMEOUT_SECONDS,
        )
