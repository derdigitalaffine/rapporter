"""Transactional recording/recomputation; no free-form metadata is accepted."""
from datetime import timedelta, timezone as datetime_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.conf import settings
from django.db import transaction
from django.db.models import F, Count, Sum, Q
from django.db.models.functions import TruncDate, Coalesce
from django.utils import timezone
from entitlements.services import resolve_entitlements
from family.models import Family, Membership
from .models import ACTIONS, FamilyContributionDaily as Daily, FamilyContributionEvent as Event


def zone_for(family):
    try:
        return ZoneInfo(family.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("Europe/Berlin")


def task_effort(task):
    value = task.estimate_minutes
    return value if value is not None and 0 <= value <= 10080 else None


def task_completion_key(task_id, when):
    return f"task-completion:{task_id}:{when.astimezone(datetime_timezone.utc).isoformat()}"


def retention_days():
    return max(730, int(getattr(settings, "STATISTICS_RETENTION_DAYS", 730)))


def _bucket(event, family):
    return dict(family=family, local_date=event.occurred_at.astimezone(zone_for(family)).date(),
                actor_key=str(event.actor_membership_id) if event.actor_membership_id else "unknown",
                actor_membership_id=event.actor_membership_id, domain=event.domain, action=event.action)


def _increment(event, family):
    row, _ = Daily.objects.get_or_create(**_bucket(event, family))
    Daily.objects.filter(pk=row.pk).update(count=F("count") + 1,
        effort_minutes_sum=F("effort_minutes_sum") + (event.effort_minutes or 0),
        effort_coverage_count=F("effort_coverage_count") + int(event.effort_minutes is not None))


@transaction.atomic
def record(*, family, domain, action, entity_type, entity_id, occurred_at,
           idempotency_key, actor=None, effort_minutes=None, source="ui"):
    if (domain, action, entity_type) not in ACTIONS or source not in {"ui", "automation", "import", "system"}:
        raise ValueError("Unsupported contribution contract")
    if timezone.is_naive(occurred_at) or not idempotency_key or len(idempotency_key) > 160:
        raise ValueError("Aware time and stable idempotency key required")
    if effort_minutes is not None and (isinstance(effort_minutes, bool) or not isinstance(effort_minutes, int) or not 0 <= effort_minutes <= 10080):
        raise ValueError("Invalid effort")
    if occurred_at < timezone.now() - timedelta(days=retention_days()):
        return None
    family = Family.objects.select_for_update().get(pk=family.pk)
    # Collection stops immediately on downgrade. Pre-commercial VIP is canonical.
    if "statistics" not in resolve_entitlements(family).capabilities:
        return None
    membership = Membership.objects.filter(family=family, user=actor).first() if actor else None
    event, created = Event.objects.get_or_create(family=family, idempotency_key=idempotency_key, defaults=dict(
        domain=domain, action=action, entity_type=entity_type, entity_id=entity_id,
        actor_user=actor if membership else None, actor_membership=membership,
        occurred_at=occurred_at, effort_minutes=effort_minutes, source=source,
        attribution_finalized=bool(membership) or source != "ui"))
    if created:
        _increment(event, family)
    return event


@transaction.atomic
def recompute(family):
    family = Family.objects.select_for_update().get(pk=family.pk)
    cutoff = timezone.now() - timedelta(days=retention_days())
    Event.objects.filter(family=family, occurred_at__lt=cutoff).delete()
    Daily.objects.filter(family=family).delete()
    groups = Event.objects.filter(family=family).annotate(day=TruncDate("occurred_at", tzinfo=zone_for(family))).values("day", "actor_membership_id", "domain", "action").annotate(total=Count("id"), minutes=Coalesce(Sum("effort_minutes"), 0), coverage=Count("id", filter=Q(effort_minutes__isnull=False)))
    Daily.objects.bulk_create([Daily(family=family, local_date=row["day"], actor_membership_id=row["actor_membership_id"], actor_key=str(row["actor_membership_id"]) if row["actor_membership_id"] else "unknown", domain=row["domain"], action=row["action"], count=row["total"], effort_minutes_sum=row["minutes"], effort_coverage_count=row["coverage"]) for row in groups], batch_size=1000)


@transaction.atomic
def remove_entity(family_id, entity_type, entity_id):
    family = Family.objects.select_for_update().filter(pk=family_id).first()
    if family and Event.objects.filter(family=family, entity_type=entity_type, entity_id=entity_id).exists():
        Event.objects.filter(family=family, entity_type=entity_type, entity_id=entity_id).delete()
        recompute(family)


def prune_expired():
    cutoff = timezone.now() - timedelta(days=retention_days())
    ids = list(Event.objects.filter(occurred_at__lt=cutoff).values_list("family_id", flat=True).distinct())
    for family in Family.objects.filter(pk__in=ids):
        recompute(family)
    return len(ids)
