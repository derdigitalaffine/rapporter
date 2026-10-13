"""Shared bounded smartphone image decoding; adapters own output/storage policy."""
import io
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_IMAGE_PIXELS = 60_000_000
MAX_SOURCE_DIMENSION = 16_384
IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "HEIF"})


def read_image_upload(upload):
    if getattr(upload, "size", 0) > MAX_IMAGE_BYTES:
        raise ValueError("Das Bild darf höchstens 30 MB groß sein.")
    data = upload.read(MAX_IMAGE_BYTES + 1)
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Ungültige Bildgröße. Maximal 30 MB.")
    return data


def decode_image(data):
    """Validate content before pixel decoding, orient it and drop metadata."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Ungültige Bildgröße. Maximal 30 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                width, height = probe.size
                if (probe.format not in IMAGE_FORMATS or width * height > MAX_IMAGE_PIXELS
                        or max(width, height) > MAX_SOURCE_DIMENSION or min(width, height) < 1):
                    raise ValueError()
                probe.verify()
            with Image.open(io.BytesIO(data)) as source:
                oriented = ImageOps.exif_transpose(source)
                oriented.load()
                mode = "RGBA" if "A" in oriented.getbands() else "RGB"
                clean = Image.new(mode, oriented.size)
                clean.paste(oriented.convert(mode))
                return clean
    except (ValueError, OSError, EOFError, UnidentifiedImageError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Ungültiges Bild. JPEG, PNG, WebP oder HEIC/HEIF bis 60 Megapixel und 16384 Pixel je Seite.") from exc
