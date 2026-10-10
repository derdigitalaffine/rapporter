"""Private canonical document storage and content validation.

This layer intentionally does not perform OCR. It validates and canonicalizes the
stored file; OCR/processing is provided by the separate document-processing core.
"""
from dataclasses import dataclass
from hashlib import sha256
import io
import warnings

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from rest_framework.exceptions import ValidationError

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
MAX_PIXELS = 32_000_000
MAX_IMAGE_DIMENSION = 2600
MAX_PDF_PAGES = 300


@dataclass(frozen=True)
class CanonicalDocument:
    content: bytes
    mime_type: str
    extension: str
    page_count: int
    sha256: str


def _read_upload(upload):
    size = getattr(upload, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "Die Datei ist zu groß. Maximal 30 MB."})
    data = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "Die Datei ist zu groß. Maximal 30 MB."})
    if not data:
        raise ValidationError({"file": "Die Datei ist leer."})
    return data


def _canonicalize_pdf(data):
    # PDFs remain byte-identical in the storage core. This avoids rasterizing born-
    # digital files and guarantees that existing digital signatures are preserved.
    if not data.startswith(b"%PDF-"):
        raise ValidationError({"file": "Ungültiges PDF."})
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise ValidationError({"file": "Passwortgeschützte PDFs werden noch nicht unterstützt."})
        page_count = len(reader.pages)
    except ValidationError:
        raise
    except (PdfReadError, ValueError, OSError, EOFError) as exc:
        raise ValidationError({"file": "Das PDF konnte nicht sicher gelesen werden."}) from exc
    if page_count < 1 or page_count > MAX_PDF_PAGES:
        raise ValidationError({"file": f"PDFs dürfen höchstens {MAX_PDF_PAGES} Seiten enthalten."})
    return data, "application/pdf", "pdf", page_count


def _canonicalize_image(data):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > MAX_PIXELS:
                    raise ValueError()
                source.verify()
            with Image.open(io.BytesIO(data)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError()
                image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                clean = Image.new("RGB", image.size)
                clean.paste(image)
                output = io.BytesIO()
                clean.save(output, "WEBP", quality=86, method=4)
                return output.getvalue(), "image/webp", "webp", 1
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValidationError({"file": "Ungültiges Bild. Erlaubt sind JPEG, PNG oder WebP bis 32 Megapixel."}) from exc


def canonicalize_upload(upload):
    data = _read_upload(upload)
    if data.startswith(b"%PDF-"):
        content, mime_type, extension, page_count = _canonicalize_pdf(data)
    else:
        content, mime_type, extension, page_count = _canonicalize_image(data)
    digest = sha256(content).hexdigest()
    return CanonicalDocument(content, mime_type, extension, page_count, digest)


def canonical_storage_key(document_id, digest, extension):
    # No user-controlled filename ever becomes part of the storage path.
    return f"private-documents/{document_id}/{digest}.{extension}"


def store_canonical(document_id, canonical):
    key = canonical_storage_key(document_id, canonical.sha256, canonical.extension)
    saved = default_storage.save(key, ContentFile(canonical.content))
    if saved != key:
        # The document UUID makes collisions unexpected; never silently accept a
        # renamed path because lifecycle code relies on an exact canonical key.
        default_storage.delete(saved)
        raise RuntimeError("Canonical document storage key collision")
    return key


def open_canonical(key):
    return default_storage.open(key, "rb")


def remove_canonical(key):
    if key:
        default_storage.delete(key)
