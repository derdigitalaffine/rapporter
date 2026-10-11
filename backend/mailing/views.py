from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from family.superadmin_views import IsSuperAdmin

from .models import TransactionalEmail
from .service import mail_health_summary
from .smtp_config import public_config


MAX_JOURNAL_ROWS = 200


def _bounded_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 100
    return max(1, min(MAX_JOURNAL_ROWS, parsed))


def _recipient_hint(value):
    value = str(value or "").strip()
    if "@" not in value:
        return ""
    local, domain = value.rsplit("@", 1)
    labels = domain.split(".")
    first = labels[0] if labels else ""
    suffix = f".{'.'.join(labels[1:])}" if len(labels) > 1 else ""
    return f"{local[:1]}***@{first[:1]}***{suffix}"


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_mail_health(request):
    """Expose only the redacted operational mail summary to superadmins."""
    summary = mail_health_summary()
    summary["configured"] = public_config()["configured"]
    return Response(summary)


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_mail_journal(request):
    """Return redacted delivery history without render context, tokens or full recipients."""
    rows = TransactionalEmail.objects.all().order_by("-created_at")
    requested_status = str(request.query_params.get("status") or "").strip()
    if requested_status in TransactionalEmail.Status.values:
        rows = rows.filter(status=requested_status)
    total = rows.count()
    limit = _bounded_limit(request.query_params.get("limit"))
    payload = []
    for row in rows[:limit]:
        payload.append(
            {
                "id": str(row.id),
                "template_key": row.template_key,
                "locale": row.locale,
                "status": row.status,
                "attempt_count": row.attempt_count,
                "last_error_code": row.last_error_code,
                "recipient_hint": _recipient_hint(row.recipient),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "sent_at": row.sent_at,
                "payload_cleared_at": row.payload_cleared_at,
            }
        )
    return Response({"count": total, "limit": limit, "results": payload})
