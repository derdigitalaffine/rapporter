from collections import Counter

from django.db.models import Count, Max
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from family.models import PushSubscription
from family.superadmin_views import IsSuperAdmin
from mailing.models import TransactionalEmail
from mailing.smtp_config import public_config

from .catalog import SAFE_SLUG_RE
from .models import AuditEvent
from .superadmin_views import PERIODS, _change, _rate, _window


def _audit_count(event_key, start, end):
    return AuditEvent.objects.filter(
        event_key=event_key,
        occurred_at__gte=start,
        occurred_at__lt=end,
    ).count()


def _channel_counts(prefix, start, end):
    return {
        "sent": _audit_count(f"{prefix}.sent", start, end),
        "failed": _audit_count(f"{prefix}.failed", start, end),
    }


def _failure_classes(event_key, start, end):
    counts = Counter()
    metadata_rows = AuditEvent.objects.filter(
        event_key=event_key,
        occurred_at__gte=start,
        occurred_at__lt=end,
    ).values_list("metadata", flat=True)
    for metadata in metadata_rows:
        raw = str((metadata or {}).get("error_class") or "unknown")
        key = raw if SAFE_SLUG_RE.fullmatch(raw) else "unknown"
        counts[key] += 1
    return [
        {"error_class": key, "count": count}
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _queue_status():
    counts = {value: 0 for value in TransactionalEmail.Status.values}
    rows = TransactionalEmail.objects.values("status").annotate(count=Count("id"))
    for row in rows:
        if row["status"] in counts:
            counts[row["status"]] = row["count"]
    return counts


def _push_subscription_status():
    total = PushSubscription.objects.count()
    active = PushSubscription.objects.filter(active=True).count()
    return {"total": total, "active": active, "inactive": total - active}


def _last_success(event_key):
    return AuditEvent.objects.filter(event_key=event_key).aggregate(last=Max("occurred_at"))["last"]


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_delivery_summary(request):
    period = str(request.query_params.get("period") or "30d").lower()
    days = PERIODS.get(period)
    if not days:
        return Response(
            {"detail": "Unsupported analytics period.", "allowed_periods": list(PERIODS)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    start, end, previous_start = _window(days)
    mail = _channel_counts("mail", start, end)
    previous_mail = _channel_counts("mail", previous_start, start)
    push = _channel_counts("push", start, end)
    previous_push = _channel_counts("push", previous_start, start)
    smtp = public_config()

    return Response(
        {
            "period": {
                "key": period,
                "days": days,
                "start": start,
                "end": end,
                "comparison_start": previous_start,
                "timezone": "UTC",
            },
            "mail": {
                "smtp_configured": bool(smtp["configured"]),
                "current_outbox": _queue_status(),
                "sent": _change(mail["sent"], previous_mail["sent"]),
                "failed": _change(mail["failed"], previous_mail["failed"]),
                "success_rate_pct": _rate(mail["sent"], mail["sent"] + mail["failed"]),
                "failure_classes": _failure_classes("mail.failed", start, end),
                "last_successful_delivery": _last_success("mail.sent"),
            },
            "push": {
                "subscriptions": _push_subscription_status(),
                "sent": _change(push["sent"], previous_push["sent"]),
                "failed": _change(push["failed"], previous_push["failed"]),
                "success_rate_pct": _rate(push["sent"], push["sent"] + push["failed"]),
                "failure_classes": _failure_classes("push.failed", start, end),
                "last_successful_delivery": _last_success("push.sent"),
            },
            "definitions": {
                "smtp_configured": "Whether the effective mail transport is configured; no SMTP credentials are exposed.",
                "current_outbox": "Current transactional mail rows grouped only by queue status.",
                "push_subscriptions": "Current canonical push subscriptions grouped only by active state; endpoint and key material are not exposed.",
                "success_rate_pct": "Sent events divided by sent plus failed events for the selected period; null when there are no delivery events.",
                "failure_classes": "Allow-listed operational error classes from canonical telemetry; recipients and message content are never returned.",
                "privacy": "The endpoint returns aggregate operational metadata only and does not serialize recipients, push endpoints/keys, message context, notification titles/bodies, tokens, or private family content.",
            },
        }
    )
