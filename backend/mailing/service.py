import hashlib
import hmac
import smtplib
import uuid
from datetime import timedelta
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from .models import TransactionalEmail

LEASE_SECONDS = 120
MAX_ATTEMPTS = 6
BASE_RETRY_SECONDS = 30
BLOCKED_CONTEXT_PARTS = (
    "token", "password", "secret", "challenge", "credential", "cookie",
    "authorization", "private_key", "raw_html", "raw_body",
)

TEMPLATE_SPECS = {
    "email.verify": {
        "de": ("E-Mail-Adresse bestätigen", "E-Mail-Adresse bestätigen", "Bestätige deine E-Mail-Adresse für FamilyOS."),
        "en": ("Verify your email address", "Verify your email address", "Confirm your email address for FamilyOS."),
    },
    "password.reset": {
        "de": ("Passwort zurücksetzen", "Passwort zurücksetzen", "Du hast einen Link zum Zurücksetzen deines FamilyOS-Passworts angefordert."),
        "en": ("Reset your password", "Reset your password", "You requested a link to reset your FamilyOS password."),
    },
    "password.changed": {
        "de": ("Passwort geändert", "Passwort geändert", "Dein FamilyOS-Passwort wurde geändert."),
        "en": ("Password changed", "Password changed", "Your FamilyOS password was changed."),
    },
    "email.changed": {
        "de": ("E-Mail-Adresse geändert", "E-Mail-Adresse geändert", "Die primäre E-Mail-Adresse deines FamilyOS-Kontos wurde geändert."),
        "en": ("Email address changed", "Email address changed", "The primary email address of your FamilyOS account was changed."),
    },
    "family.invitation": {
        "de": ("Einladung zu FamilyOS", "Du wurdest eingeladen", "Du hast eine Einladung zu einer Familie in FamilyOS erhalten."),
        "en": ("FamilyOS invitation", "You have been invited", "You received an invitation to a family in FamilyOS."),
    },
    "passkey.added": {
        "de": ("Passkey hinzugefügt", "Neuer Passkey", "Für dein FamilyOS-Konto wurde ein Passkey hinzugefügt."),
        "en": ("Passkey added", "New passkey", "A passkey was added to your FamilyOS account."),
    },
    "passkey.removed": {
        "de": ("Passkey entfernt", "Passkey entfernt", "Von deinem FamilyOS-Konto wurde ein Passkey entfernt."),
        "en": ("Passkey removed", "Passkey removed", "A passkey was removed from your FamilyOS account."),
    },
    "session.created": {
        "de": ("Neue Anmeldung", "Neue Anmeldung", "Eine neue Sitzung wurde für dein FamilyOS-Konto erstellt."),
        "en": ("New sign-in", "New sign-in", "A new session was created for your FamilyOS account."),
    },
    "session.revoked": {
        "de": ("Sitzung beendet", "Sitzung beendet", "Eine Sitzung deines FamilyOS-Kontos wurde beendet."),
        "en": ("Session ended", "Session ended", "A session of your FamilyOS account was ended."),
    },
}

_REFERENCE_RESOLVERS = {}


class IdempotencyConflictError(ValueError):
    """The same message key was reused for a semantically different delivery."""


def register_reference_resolver(reference_type, resolver):
    _REFERENCE_RESOLVERS[reference_type] = resolver


def _recipient_hash(recipient):
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), recipient.strip().lower().encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _validate_context(context):
    if not isinstance(context, dict):
        raise ValueError("Mail context must be a dictionary.")
    for key, value in context.items():
        lowered = str(key).lower()
        if any(part in lowered for part in BLOCKED_CONTEXT_PARTS):
            raise ValueError(f"Sensitive mail context key is not allowed: {key}")
        if isinstance(value, (dict, list, tuple, set)):
            raise ValueError(f"Nested mail context is not allowed: {key}")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"Unsupported mail context value: {key}")
        if isinstance(value, str) and len(value) > 1000:
            raise ValueError(f"Mail context value is too long: {key}")


def _assert_same_delivery(row, *, template_key, locale, recipient_hash, reference_type, reference_id):
    expected = (
        template_key,
        locale,
        recipient_hash,
        reference_type,
        reference_id,
    )
    actual = (
        row.template_key,
        row.locale,
        row.recipient_hash,
        row.reference_type,
        row.reference_id,
    )
    if actual != expected:
        raise IdempotencyConflictError("Transactional mail message_key is already used for a different delivery.")


def enqueue_transactional_email(*, message_key, template_key, recipient, locale="de", context=None,
                                reference_type="", reference_id=""):
    if template_key not in TEMPLATE_SPECS:
        raise ValueError(f"Unknown transactional mail template: {template_key}")
    normalized_recipient = recipient.strip().lower()
    if not normalized_recipient:
        raise ValueError("Recipient is required.")
    context = context or {}
    _validate_context(context)
    locale = "en" if str(locale).lower().startswith("en") else "de"
    reference_type = str(reference_type or "")
    reference_id = str(reference_id or "")
    recipient_hash = _recipient_hash(normalized_recipient)
    now = timezone.now()
    row, created = TransactionalEmail.objects.get_or_create(
        message_key=message_key,
        defaults={
            "template_key": template_key,
            "locale": locale,
            "recipient": normalized_recipient,
            "recipient_hash": recipient_hash,
            "context": context,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "next_attempt_at": now,
        },
    )
    if not created:
        _assert_same_delivery(
            row,
            template_key=template_key,
            locale=locale,
            recipient_hash=recipient_hash,
            reference_type=reference_type,
            reference_id=reference_id,
        )
    return row


def _safe_app_url(path):
    base = getattr(settings, "APP_URL", "").strip().rstrip("/") + "/"
    if not base or base == "/":
        return ""
    parsed = urlparse(path or "")
    if parsed.scheme or parsed.netloc:
        return ""
    if not str(path or "").startswith("/"):
        return ""
    return urljoin(base, str(path).lstrip("/"))


def _resolve_action(row):
    if not row.reference_type:
        return ""
    resolver = _REFERENCE_RESOLVERS.get(row.reference_type)
    if not resolver:
        return ""
    path = resolver(row.reference_id)
    return _safe_app_url(path)


def render_transactional_email(row):
    locale = row.locale if row.locale in ("de", "en") else "de"
    spec = TEMPLATE_SPECS[row.template_key][locale]
    subject, title, body = spec
    action_url = _resolve_action(row)
    action_label = row.context.get("action_label", "")
    render_context = {
        "lang": locale,
        "title": title,
        "body": body,
        "action_url": action_url,
        "action_label": action_label,
        "default_action_label": "Open FamilyOS" if locale == "en" else "FamilyOS öffnen",
        "details": row.context.get("details", ""),
        "support_text": row.context.get("support_text", ""),
    }
    text = render_to_string("mailing/transactional.txt", render_context)
    html = render_to_string("mailing/transactional.html", render_context)
    return subject, text, html


def _message_id(row):
    digest = hashlib.sha256(row.message_key.encode("utf-8")).hexdigest()[:32]
    host = urlparse(getattr(settings, "APP_URL", "")).hostname or "familyos.local"
    return f"<{digest}@{host}>"


def _clear_terminal_failure(row, *, now, error_code):
    row.status = TransactionalEmail.Status.FAILED
    row.last_error_code = error_code
    row.payload_cleared_at = now
    row.recipient = ""
    row.context = {}
    row.lease_token = None
    row.lease_expires_at = None


def claim_due_email(now=None):
    now = now or timezone.now()
    due = Q(status__in=[TransactionalEmail.Status.QUEUED, TransactionalEmail.Status.RETRY], next_attempt_at__lte=now)
    expired_lease = Q(status=TransactionalEmail.Status.SENDING, lease_expires_at__lte=now)
    claimable = due | expired_lease
    with transaction.atomic():
        exhausted = (
            TransactionalEmail.objects.select_for_update(skip_locked=True)
            .filter(claimable, attempt_count__gte=MAX_ATTEMPTS)
            .order_by("next_attempt_at", "created_at")
            .first()
        )
        if exhausted:
            _clear_terminal_failure(exhausted, now=now, error_code="attempts_exhausted")
            exhausted.save(update_fields=[
                "status", "last_error_code", "payload_cleared_at", "recipient", "context",
                "lease_token", "lease_expires_at", "updated_at",
            ])

        row = (
            TransactionalEmail.objects.select_for_update(skip_locked=True)
            .filter(claimable, attempt_count__lt=MAX_ATTEMPTS)
            .order_by("next_attempt_at", "created_at")
            .first()
        )
        if not row:
            return None
        row.status = TransactionalEmail.Status.SENDING
        row.attempt_count += 1
        row.lease_token = uuid.uuid4()
        row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        row.save(update_fields=["status", "attempt_count", "lease_token", "lease_expires_at", "updated_at"])
        return row


def _classify_error(exc):
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "recipient_rejected", False
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "smtp_auth", False
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "smtp_unsupported", False
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError)):
        return "transport", True
    if isinstance(exc, smtplib.SMTPResponseException):
        retry = 400 <= int(exc.smtp_code or 0) < 500
        return f"smtp_{int(exc.smtp_code or 0)}", retry
    return exc.__class__.__name__.lower()[:80], True


def _finalize_success(row):
    now = timezone.now()
    with transaction.atomic():
        locked = TransactionalEmail.objects.select_for_update().get(pk=row.pk)
        if locked.lease_token != row.lease_token or locked.status != TransactionalEmail.Status.SENDING:
            return False
        locked.status = TransactionalEmail.Status.SENT
        locked.sent_at = now
        locked.payload_cleared_at = now
        locked.recipient = ""
        locked.context = {}
        locked.last_error_code = ""
        locked.lease_token = None
        locked.lease_expires_at = None
        locked.save(update_fields=[
            "status", "sent_at", "payload_cleared_at", "recipient", "context", "last_error_code",
            "lease_token", "lease_expires_at", "updated_at",
        ])
    return True


def _finalize_failure(row, exc):
    error_code, retryable = _classify_error(exc)
    now = timezone.now()
    with transaction.atomic():
        locked = TransactionalEmail.objects.select_for_update().get(pk=row.pk)
        if locked.lease_token != row.lease_token or locked.status != TransactionalEmail.Status.SENDING:
            return False
        exhausted = locked.attempt_count >= MAX_ATTEMPTS
        if retryable and not exhausted:
            locked.status = TransactionalEmail.Status.RETRY
            delay = BASE_RETRY_SECONDS * (2 ** max(0, locked.attempt_count - 1))
            locked.next_attempt_at = now + timedelta(seconds=min(delay, 3600))
            locked.last_error_code = error_code
            locked.lease_token = None
            locked.lease_expires_at = None
            locked.save(update_fields=[
                "status", "next_attempt_at", "last_error_code", "lease_token", "lease_expires_at", "updated_at",
            ])
        else:
            _clear_terminal_failure(locked, now=now, error_code=error_code)
            locked.save(update_fields=[
                "status", "last_error_code", "payload_cleared_at", "recipient", "context",
                "lease_token", "lease_expires_at", "updated_at",
            ])
    return True


def process_one_transactional_email():
    row = claim_due_email()
    if not row:
        return False
    try:
        subject, text, html = render_transactional_email(row)
        message = EmailMultiAlternatives(
            subject=subject,
            body=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[row.recipient],
            reply_to=[settings.EMAIL_REPLY_TO] if getattr(settings, "EMAIL_REPLY_TO", "") else None,
            headers={"Message-ID": _message_id(row)},
        )
        message.attach_alternative(html, "text/html")
        sent = message.send(fail_silently=False)
        if sent != 1:
            raise RuntimeError("mail_backend_did_not_accept_message")
    except Exception as exc:  # backend/network errors are reduced to an allow-listed error class
        _finalize_failure(row, exc)
        return True
    _finalize_success(row)
    return True


def mail_is_configured():
    backend = getattr(settings, "EMAIL_BACKEND", "")
    if backend.endswith("dummy.EmailBackend"):
        return False
    if backend.endswith("smtp.EmailBackend"):
        return bool(getattr(settings, "EMAIL_HOST", "") and getattr(settings, "DEFAULT_FROM_EMAIL", ""))
    return True


def mail_health_summary():
    rows = TransactionalEmail.objects.all()
    counts = {status: rows.filter(status=status).count() for status, _ in TransactionalEmail.Status.choices}
    sent = list(rows.filter(status=TransactionalEmail.Status.SENT, sent_at__isnull=False).order_by("-sent_at")[:200])
    latencies = sorted(max(0.0, (row.sent_at - row.created_at).total_seconds()) for row in sent)

    def percentile(fraction):
        if not latencies:
            return None
        return round(latencies[min(len(latencies) - 1, int((len(latencies) - 1) * fraction))], 3)

    recent_errors = list(
        rows.exclude(last_error_code="").values_list("last_error_code", flat=True).order_by("-updated_at")[:20]
    )
    last_success = rows.filter(sent_at__isnull=False).order_by("-sent_at").values_list("sent_at", flat=True).first()
    return {
        "configured": mail_is_configured(),
        "counts": counts,
        "last_success_at": last_success,
        "latency_seconds": {"p50": percentile(0.50), "p95": percentile(0.95)},
        "recent_error_classes": sorted(set(recent_errors)),
    }
