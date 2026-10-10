"""Compatibility adapter for legacy domains not yet migrated to ``Document``.

This module deliberately contains no domain semantics. It lets remaining legacy
BinaryField consumers reuse the canonical Document image validation,
normalization, quality assessment and adaptive OCR implementation while their
schema migration is scheduled separately.
"""
from io import BytesIO

from PIL import Image
from rest_framework.exceptions import ValidationError

from .extraction import _ocr_image
from .quality import assess_image
from .storage import canonicalize_upload

PUBLIC_LEGACY_WARNINGS = {"low_resolution", "dark"}


def _message(exc):
    detail = getattr(exc, "detail", exc)
    if isinstance(detail, dict):
        detail = detail.get("file") or next(iter(detail.values()), None)
    if isinstance(detail, (list, tuple)):
        detail = detail[0] if detail else None
    return str(detail or "Die Bilddatei konnte nicht sicher gelesen werden.")


def canonicalize_legacy_image(upload):
    """Return Document-Core canonical image bytes for a legacy domain upload."""
    try:
        canonical = canonicalize_upload(upload)
    except ValidationError as exc:
        raise ValueError(_message(exc)) from exc
    if not canonical.mime_type.startswith("image/"):
        raise ValueError("Nur JPEG-, PNG- oder WebP-Bilder werden unterstützt.")
    with Image.open(BytesIO(canonical.content)) as image:
        warnings = [
            warning
            for warning in assess_image(image).get("warnings", [])
            if warning in PUBLIC_LEGACY_WARNINGS
        ]
    return canonical.content, canonical.mime_type, warnings


def extract_legacy_image_text(content):
    """Run the shared adaptive OCR engine over legacy in-database image bytes."""
    with Image.open(BytesIO(content)) as source:
        source.load()
        page = _ocr_image(source.convert("RGB"), 1, heartbeat=lambda: None)
    return page["text"]
