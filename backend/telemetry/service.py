from datetime import datetime, time, timedelta, timezone as dt_timezone
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from family.models import Family, Membership

from .catalog import TelemetrySchemaError, validate_audit_event, validate_usage_event
from .models import AuditEvent, DailyRollup, UsageEvent

logger = logging.getLogger("telemetry")

METRIC_ACTIVE_USERS = "usage.active_users"
METRIC_ACTIVE_FAMILIES = "usage.active_families"
METRIC_MODULE_USERS = "usage.module_users"
METRIC_AUDIT_EVENT_COUNT = "audit.event_count"


def _aware_utc(value):
    value = value or timezone.now()
    if timezone.is_naive(value):
        value = timezone.make_aware(value, dt_timezone.utc)
    return value.astimezone(dt_timezone.utc)


def _hour_bucket(value):
    value = _aware_utc(value)
    return value.replace(minute=0, second=0, microsecond=0)


def record_audit_event(
    event_key,
    *,
    actor=None,
    actor_class="system",
    family=None,
    outcome="success",
    reason="",
    request_id="",
    target_type="",
    target_id="",
    metadata=None,
    occurred_at=None,
):
    clean = validate_audit_event(
        event_key,
        actor_class=actor_class,
        outcome=outcome,
        reason=reason,
        metadata=metadata,
        request_id=request_id,
        target_type=target_type,
        target_id=target_id,
    )
    if actor_class == "system" and actor is not None:
        raise TelemetrySchemaError("system_actor_must_be_empty")
    if actor_class in {"user", "superadmin"} and actor is None:
        raise TelemetrySchemaError("actor_required")
    return AuditEvent.objects.create(
        occurred_at=_aware_utc(occurred_at),
        schema_version=1,
        actor=actor,
        family=family,
        **clean,
    )


def try_record_audit_event(event_key, **kwargs):
    try:
        return record_audit_event(event_key, **kwargs)
    except Exception as exc:
        logger.error(
            "audit_event_write_failed event_key=%s error_class=%s",
            event_key,
            exc.__class__.__name__,
        )
        return None


def record_usage_event(event_key, *, user, family, dimension_key="", occurred_at=None):
    event_key, dimension_key = validate_usage_event(event_key, dimension_key)
    if user is None or not getattr(user, "pk", None):
        raise TelemetrySchemaError("usage_user_required")
    if family is None or not getattr(family, "pk", None):
        raise TelemetrySchemaError("usage_family_required")
    if not Membership.objects.filter(
        user=user,
        family=family,
        family__status=Family.Status.ACTIVE,
    ).exists():
        raise TelemetrySchemaError("usage_family_unavailable")
    observed_at = _aware_utc(occurred_at)
    event, _created = UsageEvent.objects.get_or_create(
        user=user,
        family=family,
        event_key=event_key,
        bucket_start=_hour_bucket(observed_at),
        dimension_key=dimension_key,
        defaults={"occurred_at": observed_at},
    )
    return event


def try_record_usage_event(event_key, **kwargs):
    try:
        return record_usage_event(event_key, **kwargs)
    except Exception as exc:
        logger.error(
            "usage_event_write_failed event_key=%s error_class=%s",
            event_key,
            exc.__class__.__name__,
        )
        return None


def _day_bounds(day):
    start = datetime.combine(day, time.min, tzinfo=dt_timezone.utc)
    return start, start + timedelta(days=1)


def recompute_daily_rollups(day):
    start, end = _day_bounds(day)
    usage = UsageEvent.objects.filter(bucket_start__gte=start, bucket_start__lt=end)
    activity = usage.filter(event_key="activity.foreground")
    audit = AuditEvent.objects.filter(occurred_at__gte=start, occurred_at__lt=end)

    rows = [
        DailyRollup(
            day=day,
            metric_key=METRIC_ACTIVE_USERS,
            value=activity.values("user_id").distinct().count(),
        ),
        DailyRollup(
            day=day,
            metric_key=METRIC_ACTIVE_FAMILIES,
            value=activity.values("family_id").distinct().count(),
        ),
    ]

    for item in activity.values("family_id").annotate(value=Count("user_id", distinct=True)).order_by("family_id"):
        rows.append(
            DailyRollup(
                day=day,
                metric_key=METRIC_ACTIVE_USERS,
                family_id=item["family_id"],
                value=item["value"],
            )
        )

    modules = usage.filter(event_key="module.used")
    for item in modules.values("dimension_key").annotate(value=Count("user_id", distinct=True)).order_by("dimension_key"):
        rows.append(
            DailyRollup(
                day=day,
                metric_key=METRIC_MODULE_USERS,
                dimension_key=item["dimension_key"],
                value=item["value"],
            )
        )
    for item in (
        modules.values("family_id", "dimension_key")
        .annotate(value=Count("user_id", distinct=True))
        .order_by("family_id", "dimension_key")
    ):
        rows.append(
            DailyRollup(
                day=day,
                metric_key=METRIC_MODULE_USERS,
                family_id=item["family_id"],
                dimension_key=item["dimension_key"],
                value=item["value"],
            )
        )

    for item in audit.values("event_key", "outcome").annotate(value=Count("id")).order_by("event_key", "outcome"):
        rows.append(
            DailyRollup(
                day=day,
                metric_key=METRIC_AUDIT_EVENT_COUNT,
                dimension_key=f"{item['event_key']}:{item['outcome']}",
                value=item["value"],
            )
        )

    with transaction.atomic():
        DailyRollup.objects.filter(day=day).delete()
        DailyRollup.objects.bulk_create(rows)
    return rows


def _delete_in_batches(queryset, *, batch_size):
    deleted_total = 0
    while True:
        ids = list(queryset.order_by("occurred_at", "id").values_list("id", flat=True)[:batch_size])
        if not ids:
            return deleted_total
        deleted, _details = queryset.model.objects.filter(id__in=ids).delete()
        deleted_total += deleted


def prune_raw_events(*, now=None, batch_size=1000):
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    now = _aware_utc(now)
    usage_days = max(0, int(getattr(settings, "TELEMETRY_USAGE_RETENTION_DAYS", 60)))
    audit_days = max(0, int(getattr(settings, "TELEMETRY_AUDIT_RETENTION_DAYS", 180)))
    usage_cutoff = now - timedelta(days=usage_days)
    audit_cutoff = now - timedelta(days=audit_days)
    usage_deleted = _delete_in_batches(
        UsageEvent.objects.filter(occurred_at__lt=usage_cutoff),
        batch_size=batch_size,
    )
    audit_deleted = _delete_in_batches(
        AuditEvent.objects.filter(occurred_at__lt=audit_cutoff),
        batch_size=batch_size,
    )
    return {"usage_deleted": usage_deleted, "audit_deleted": audit_deleted}
