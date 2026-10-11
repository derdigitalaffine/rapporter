from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from family.superadmin_views import IsSuperAdmin, _enforce_sensitive_action, _rate_limited_response

from .models import ManagedSmtpConfig
from .service import _classify_error
from .smtp_config import effective_connection, effective_mail_config, encrypt_password, public_config


def _email(value, *, optional=False):
    value = str(value or "").strip()
    if optional and not value:
        return ""
    if "\r" in value or "\n" in value:
        return None
    try:
        validate_email(value)
    except ValidationError:
        return None
    return value


def _validated_payload(data, current):
    host = str(data.get("host", current.host if current else "")).strip()
    username = str(data.get("username", current.username if current else "")).strip()
    security = str(data.get("security", current.security if current else ManagedSmtpConfig.Security.STARTTLS)).strip()
    from_email = _email(data.get("from_email", current.from_email if current else ""))
    reply_to = _email(data.get("reply_to", current.reply_to if current else ""), optional=True)
    try:
        port = int(data.get("port", current.port if current else 587))
        timeout = int(data.get("timeout", current.timeout if current else 10))
    except (TypeError, ValueError):
        return None, "Port und Timeout müssen Zahlen sein."
    if not host or len(host) > 253 or any(ch.isspace() for ch in host):
        return None, "Gültiger SMTP-Host fehlt."
    if not 1 <= port <= 65535:
        return None, "SMTP-Port ist ungültig."
    if not 1 <= timeout <= 120:
        return None, "Timeout muss zwischen 1 und 120 Sekunden liegen."
    if security not in ManagedSmtpConfig.Security.values:
        return None, "Ungültige Transport-Sicherheit."
    if from_email is None or reply_to is None:
        return None, "Absender-/Reply-To-Adresse ist ungültig."
    return {"host": host, "port": port, "username": username, "security": security, "timeout": timeout,
            "from_email": from_email, "reply_to": reply_to}, None


@api_view(["GET", "PUT"])
@permission_classes([IsSuperAdmin])
def superadmin_smtp_config(request):
    if request.method == "GET":
        return Response(public_config())
    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)
    current = ManagedSmtpConfig.objects.filter(pk=1).first()
    values, error = _validated_payload(request.data, current)
    if error:
        return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
    row = current or ManagedSmtpConfig(pk=1)
    for key, value in values.items():
        setattr(row, key, value)
    row.enabled = bool(request.data.get("enabled", False))
    password = request.data.get("password")
    if password:
        row.password_encrypted = encrypt_password(password)
    if request.data.get("clear_password") is True:
        row.password_encrypted = ""
    if row.enabled and row.username and not row.password_encrypted:
        return Response({"detail": "SMTP-Passwort fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    row.save()
    return Response(public_config())


@api_view(["POST"])
@permission_classes([IsSuperAdmin])
def superadmin_smtp_test(request):
    decision = _enforce_sensitive_action(request)
    if not decision.allowed:
        return _rate_limited_response(decision)
    recipient = _email(request.data.get("recipient"))
    if recipient is None:
        return Response({"detail": "Gültige Testadresse fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    state = public_config()
    if not state["configured"]:
        return Response(
            {"detail": "Mail-Transport ist nicht konfiguriert.", "code": "mail_not_configured"},
            status=status.HTTP_409_CONFLICT,
        )
    cfg = effective_mail_config()
    if not cfg["from_email"]:
        return Response({"detail": "Kein Absender konfiguriert.", "code": "mail_not_configured"}, status=status.HTTP_409_CONFLICT)
    try:
        message = EmailMultiAlternatives(
            subject="FamilyOS SMTP-Test",
            body="Diese Testmail bestätigt, dass FamilyOS den konfigurierten Mail-Transport erreichen kann.",
            from_email=cfg["from_email"], to=[recipient],
            reply_to=[cfg["reply_to"]] if cfg["reply_to"] else None,
            connection=effective_connection(),
        )
        accepted = message.send(fail_silently=False)
        if accepted != 1:
            raise RuntimeError("mail_backend_did_not_accept_message")
    except Exception as exc:
        code, _retryable = _classify_error(exc)
        return Response({"detail": "SMTP-Test fehlgeschlagen.", "code": code}, status=status.HTTP_502_BAD_GATEWAY)
    return Response({"ok": True, "accepted": True, "source": cfg["source"]})
