from datetime import datetime, time, timezone as dt_timezone

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Max, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from family.models import IntegrationSource
from family.superadmin_views import IsSuperAdmin
from mailing.service import mail_health_summary

from .models import AuditEvent, DailyRollup, UsageEvent


UNKNOWN_HEARTBEATS = (
    "scheduler",
    "notification_worker",
    "mail_worker",
    "ocr_worker",
)


def _component(status, reason, **details):
    return {"status": status, "reason": reason, **details}


def _database_health():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            ok = cursor.fetchone() == (1,)
    except Exception:
        return _component("failing", "database_query_failed")
    return _component("healthy" if ok else "failing", "database_query_ok" if ok else "database_query_unexpected")


def _migration_health():
    try:
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        pending = [f"{migration.app_label}.{migration.name}" for migration, backwards in plan if not backwards]
    except Exception:
        return _component("unknown", "migration_state_unavailable", pending_count=None, pending=[])
    return _component(
        "healthy" if not pending else "degraded",
        "migrations_current" if not pending else "migrations_pending",
        pending_count=len(pending),
        pending=pending[:20],
        truncated=len(pending) > 20,
    )


def _integration_health():
    enabled = IntegrationSource.objects.filter(enabled=True)
    enabled_count = enabled.count()
    if enabled_count == 0:
        return _component(
            "unknown",
            "no_enabled_integrations",
            enabled=0,
            degraded=0,
            last_success_at=None,
        )

    degraded = enabled.filter(Q(consecutive_failures__gt=0) | Q(last_sync_status__in=["failed", "error"])).count()
    last_success = enabled.aggregate(last=Max("last_success_at"))["last"]
    return _component(
        "degraded" if degraded else "healthy",
        "integration_failures_present" if degraded else "integrations_operational",
        enabled=enabled_count,
        degraded=degraded,
        last_success_at=last_success,
    )


def _mail_queue_health():
    summary = mail_health_summary()
    counts = summary["counts"]
    retry = int(counts.get("retry", 0))
    failed = int(counts.get("failed", 0))
    queued = int(counts.get("queued", 0))
    sending = int(counts.get("sending", 0))
    backlog = queued + sending + retry
    degraded = retry > 0 or failed > 0
    return _component(
        "degraded" if degraded else "healthy",
        "mail_retry_or_failure_present" if degraded else "mail_queue_operational",
        configured=bool(summary["configured"]),
        backlog=backlog,
        counts={key: int(value) for key, value in counts.items()},
        latency_seconds=summary["latency_seconds"],
        last_success_at=summary["last_success_at"],
        recent_error_classes=summary["recent_error_classes"],
    )


def _telemetry_health(now):
    last_audit = AuditEvent.objects.aggregate(last=Max("occurred_at"))["last"]
    last_usage = UsageEvent.objects.aggregate(last=Max("occurred_at"))["last"]
    last_rollup = DailyRollup.objects.aggregate(day=Max("day"), updated=Max("updated_at"))

    latest_event = max((value for value in (last_audit, last_usage) if value is not None), default=None)
    event_age_seconds = None if latest_event is None else max(0, round((now - latest_event).total_seconds()))

    rollup_age_seconds = None
    if last_rollup["day"] is not None:
        rollup_end = datetime.combine(last_rollup["day"], time.max, tzinfo=dt_timezone.utc)
        rollup_age_seconds = max(0, round((now - rollup_end).total_seconds()))

    has_signal = latest_event is not None or last_rollup["day"] is not None
    return _component(
        "healthy" if has_signal else "unknown",
        "telemetry_sources_readable" if has_signal else "no_telemetry_observed",
        last_audit_event_at=last_audit,
        last_usage_event_at=last_usage,
        event_age_seconds=event_age_seconds,
        latest_rollup_day=last_rollup["day"],
        latest_rollup_updated_at=last_rollup["updated"],
        rollup_age_seconds=rollup_age_seconds,
    )


def _worker_heartbeats():
    return {
        worker: _component("unknown", "no_canonical_heartbeat_source")
        for worker in UNKNOWN_HEARTBEATS
    }


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_operations_health(request):
    now = timezone.now()
    components = {
        "database": _database_health(),
        "migrations": _migration_health(),
        "integrations": _integration_health(),
        "mail_queue": _mail_queue_health(),
        "telemetry": _telemetry_health(now),
        "workers": _worker_heartbeats(),
    }

    failing = any(value.get("status") == "failing" for key, value in components.items() if key != "workers")
    degraded = any(value.get("status") == "degraded" for key, value in components.items() if key != "workers")
    overall = "failing" if failing else "degraded" if degraded else "healthy"

    return Response(
        {
            "checked_at": now,
            "status": overall,
            "components": components,
            "definitions": {
                "unknown": "No canonical or reliable health source exists; the API does not infer a healthy state.",
                "workers": "Worker heartbeat states stay unknown until explicit canonical heartbeat data exists.",
                "privacy": "Only aggregate operational metadata is returned; integration config, mail recipients/content, tokens and private family content are never serialized.",
            },
        }
    )
