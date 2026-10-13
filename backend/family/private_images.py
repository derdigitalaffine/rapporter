"""Decode untrusted raster uploads and retain only optimized, metadata-free WebP."""
import io
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from PIL import Image
from rest_framework.exceptions import ValidationError


def optimize_image(upload, max_dimension=1600):
    from documents.images import decode_image, read_image_upload
    try:
        image = decode_image(read_image_upload(upload)).convert('RGB')
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, 'WEBP', quality=84, method=4)
        return output.getvalue(), image.width, image.height
    except ValueError as exc:
        raise ValidationError({'images': str(exc)}) from exc

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
