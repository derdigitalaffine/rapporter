"""Decode untrusted raster uploads and retain only optimized, metadata-free WebP."""
import io
import warnings
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 24_000_000

def optimize_image(upload, max_dimension=1600):
    if upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError({'images': 'JPEG, PNG oder WebP bis 10 MB.'})
    data = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError({'images': 'Das Bild ist zu groß.'})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > MAX_PIXELS:
                    raise ValueError()
                source.verify()
            with Image.open(io.BytesIO(data)) as source:
                image = ImageOps.exif_transpose(source).convert('RGB')
                image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                clean = Image.new('RGB', image.size)
                clean.paste(image)
                output = io.BytesIO()
                clean.save(output, 'WEBP', quality=84, method=4)
                return output.getvalue(), clean.width, clean.height
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError({'images': 'Ungültiges Bild. Maximal 24 Megapixel; JPEG, PNG oder WebP.'})

def image_path(key):
    # Keys are generated server-side. Never accept a path from a request.
    if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Invalid media key')
    return Path(settings.MEDIA_ROOT) / 'private-images' / f'{key}.webp'

def store_image(data):
    key = uuid4().hex
    path = image_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(data)
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return key

def remove_image(key):
    image_path(key).unlink(missing_ok=True)
