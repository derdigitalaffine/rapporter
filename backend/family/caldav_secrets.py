import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    # Match the repository's managed SMTP secret-storage strategy: encrypted at
    # rest with a deterministic Fernet key derived from the deployment secret.
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_credentials(*, server_url, username, password):
    payload = json.dumps(
        {
            "server_url": str(server_url).strip(),
            "username": str(username or ""),
            "password": str(password or ""),
        },
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_credentials(value):
    if not value:
        raise ValueError("caldav_credentials_missing")
    try:
        payload = _fernet().decrypt(value.encode("ascii"))
        data = json.loads(payload.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("caldav_credentials_unreadable") from exc
    if not isinstance(data, dict) or not data.get("server_url"):
        raise ValueError("caldav_credentials_unreadable")
    return {
        "server_url": str(data["server_url"]),
        "username": str(data.get("username") or ""),
        "password": str(data.get("password") or ""),
    }
