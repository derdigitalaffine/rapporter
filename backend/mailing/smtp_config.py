import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.mail import get_connection

from .models import ManagedSmtpConfig

ROUTING_BACKEND = "mailing.backends.ManagedRoutingEmailBackend"


def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_password(value):
    return _fernet().encrypt(str(value).encode("utf-8")).decode("ascii") if value else ""


def decrypt_password(value):
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        raise ValueError("smtp_password_unreadable")


def managed_config():
    return ManagedSmtpConfig.objects.filter(pk=1, enabled=True).first()


def effective_mail_config():
    row = managed_config()
    if row:
        return {
            "source": "superadmin", "backend": "django.core.mail.backends.smtp.EmailBackend",
            "host": row.host, "port": row.port, "username": row.username,
            "password": decrypt_password(row.password_encrypted),
            "use_tls": row.security == ManagedSmtpConfig.Security.STARTTLS,
            "use_ssl": row.security == ManagedSmtpConfig.Security.SSL,
            "timeout": row.timeout, "from_email": row.from_email, "reply_to": row.reply_to,
        }
    current_backend = getattr(settings, "EMAIL_BACKEND", "")
    backend = getattr(settings, "EMAIL_ENV_BACKEND", current_backend) if current_backend == ROUTING_BACKEND else current_backend
    return {
        "source": "environment", "backend": backend,
        "host": getattr(settings, "EMAIL_HOST", ""), "port": getattr(settings, "EMAIL_PORT", 25),
        "username": getattr(settings, "EMAIL_HOST_USER", ""), "password": getattr(settings, "EMAIL_HOST_PASSWORD", ""),
        "use_tls": bool(getattr(settings, "EMAIL_USE_TLS", False)), "use_ssl": bool(getattr(settings, "EMAIL_USE_SSL", False)),
        "timeout": getattr(settings, "EMAIL_TIMEOUT", 10), "from_email": getattr(settings, "DEFAULT_FROM_EMAIL", ""),
        "reply_to": getattr(settings, "EMAIL_REPLY_TO", ""),
    }


def effective_connection():
    cfg = effective_mail_config()
    if cfg["source"] == "superadmin":
        return get_connection(backend=cfg["backend"], host=cfg["host"], port=cfg["port"], username=cfg["username"],
                              password=cfg["password"], use_tls=cfg["use_tls"], use_ssl=cfg["use_ssl"],
                              timeout=cfg["timeout"], fail_silently=False)
    return get_connection(backend=cfg["backend"], fail_silently=False)


def public_config():
    row = ManagedSmtpConfig.objects.filter(pk=1).first()
    effective = effective_mail_config()
    return {
        "enabled": bool(row and row.enabled), "host": row.host if row else "", "port": row.port if row else 587,
        "username": row.username if row else "", "password_set": bool(row and row.password_encrypted),
        "security": row.security if row else ManagedSmtpConfig.Security.STARTTLS, "timeout": row.timeout if row else 10,
        "from_email": row.from_email if row else "", "reply_to": row.reply_to if row else "",
        "effective_source": effective["source"],
        "configured": bool(effective["host"] and effective["from_email"]) if effective["backend"].endswith("smtp.EmailBackend") else not effective["backend"].endswith("dummy.EmailBackend"),
    }
