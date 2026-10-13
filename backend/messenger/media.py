"""Chat-specific limits with the canonical private document validator and storage."""
import hashlib
import io
import uuid
from pathlib import PurePath

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError

from documents.storage import CanonicalDocument, canonicalize_upload, remove_canonical, store_canonical
from .models import ChatAttachment


def prepare_uploads(files):
    result = []
    for upload in files:
        if upload.size > 10 * 1024 * 1024:
            raise ValidationError({"files": "Maximal 10 MB pro Datei."})
        data = upload.read(10 * 1024 * 1024 + 1)
        if not data or len(data) > 10 * 1024 * 1024:
            raise ValidationError({"files": "Ungültige Dateigröße."})
        mime = str(upload.content_type or "").split(";", 1)[0]
        if mime in {"audio/webm", "audio/ogg", "audio/mp4"}:
            valid = (mime == "audio/webm" and data.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in data[:256]) or (mime == "audio/ogg" and data.startswith(b"OggS") and b"OpusHead" in data[:256]) or (mime == "audio/mp4" and data[4:8] == b"ftyp")
            if not valid or len(data) > 8 * 1024 * 1024:
                raise ValidationError({"files": "Ungültige Sprachnachricht."})
            extension = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a"}[mime]
            canonical = CanonicalDocument(data, mime, extension, 1, hashlib.sha256(data).hexdigest())
            kind = "audio"
        else:
            canonical = canonicalize_upload(SimpleUploadedFile("upload", data))
            kind = "pdf" if canonical.mime_type == "application/pdf" else "image"
        name = PurePath(str(upload.name or "file").replace("\\", "/")).name
        name = "".join(c for c in name if ord(c) >= 32 and c not in '\"').strip()[:160] or "file"
        result.append((canonical, kind, name))
    return result


def save_uploads(message, uploads):
    keys = []
    try:
        for canonical, kind, name in uploads:
            attachment_id = uuid.uuid4()
            key = store_canonical(attachment_id, canonical)
            keys.append(key)
            ChatAttachment.objects.create(id=attachment_id, message=message, name=name, kind=kind, mime_type=canonical.mime_type, storage_key=key, size=len(canonical.content))
    except Exception:
        for key in keys:
            remove_canonical(key)
        raise
