from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .family_modules import care_access
from .models import BabyCareLog, BabyProfile, BabyViewState, CareHandoverNote, HandoverRead


MAX_BACKDATE = timedelta(days=120)


def _baby_for_user(user, baby_id, scope="care"):
    baby = BabyProfile.objects.select_related("family", "membership").filter(pk=baby_id, active=True).first()
    if not baby:
        raise ValidationError({"baby": "Baby profile not found."})
    membership, access = care_access(user, baby.family, scope)
    return baby, membership, access


def _validate_times(started_at, ended_at=None):
    now = timezone.now()
    if started_at > now + timedelta(minutes=5):
        raise ValidationError({"started_at": "Care events cannot start in the future."})
    if started_at < now - MAX_BACKDATE:
        raise ValidationError({"started_at": "Care events can be backdated by at most 120 days."})
    if ended_at and ended_at < started_at:
        raise ValidationError({"ended_at": "End time must be after start time."})
    if ended_at and ended_at > now + timedelta(minutes=5):
        raise ValidationError({"ended_at": "Care events cannot end in the future."})


def _validate_value(kind, value):
    value = value or {}
    if not isinstance(value, dict):
        raise ValidationError({"value": "Use an object for care details."})
    if kind == BabyCareLog.Kind.BOTTLE:
        ml = value.get("ml")
        if ml is not None and not 0 < float(ml) <= 1000:
            raise ValidationError({"value": "Bottle amount must be between 0 and 1000 ml."})
    if kind == BabyCareLog.Kind.PUMP:
        ml = value.get("ml")
        if ml is not None and not 0 < float(ml) <= 2000:
            raise ValidationError({"value": "Pumped amount must be between 0 and 2000 ml."})
    if kind == BabyCareLog.Kind.TEMPERATURE:
        celsius = value.get("celsius")
        if celsius is not None and not 30 <= float(celsius) <= 45:
            raise ValidationError({"value": "Temperature must be between 30 and 45 °C."})
    if kind == BabyCareLog.Kind.DIAPER:
        diaper_type = value.get("type")
        if diaper_type and diaper_type not in {"wet", "dirty", "mixed", "dry"}:
            raise ValidationError({"value": "Unknown diaper type."})
    if kind == BabyCareLog.Kind.BREASTFEED:
        side = value.get("side")
        if side and side not in {"left", "right", "both", "unknown"}:
            raise ValidationError({"value": "Unknown breastfeeding side."})
    return value


@transaction.atomic
def record_care_log(user, baby_id, *, kind, started_at, ended_at=None, value=None, client_event_id=None):
    baby, _, access = _baby_for_user(user, baby_id, "care")
    if not access.can_log_care:
        raise PermissionDenied("Care logging is not permitted.")
    if kind not in BabyCareLog.Kind.values:
        raise ValidationError({"kind": "Unknown care event type."})
    _validate_times(started_at, ended_at)
    value = _validate_value(kind, value)
    if client_event_id:
        existing = BabyCareLog.objects.select_for_update().filter(baby=baby, client_event_id=client_event_id).first()
        if existing:
            return existing, False
    row = BabyCareLog.objects.create(
        family=baby.family,
        baby=baby,
        kind=kind,
        started_at=started_at,
        ended_at=ended_at,
        value=value,
        created_by=user,
        client_event_id=client_event_id,
    )
    return row, True


@transaction.atomic
def update_care_log(user, log_id, *, expected_version, started_at=None, ended_at=None, value=None):
    row = BabyCareLog.objects.select_for_update().select_related("baby__family").filter(pk=log_id).first()
    if not row:
        raise ValidationError({"care_log": "Care event not found."})
    _, _, access = _baby_for_user(user, row.baby_id, "care")
    if not access.can_log_care:
        raise PermissionDenied("Care logging is not permitted.")
    if int(expected_version) != row.version:
        raise ValidationError({"version": f"Care event changed on another device (current version {row.version})."})
    next_start = started_at or row.started_at
    next_end = row.ended_at if ended_at is None else ended_at
    _validate_times(next_start, next_end)
    row.started_at = next_start
    row.ended_at = next_end
    if value is not None:
        row.value = _validate_value(row.kind, value)
    row.corrected_at = timezone.now()
    row.version += 1
    row.save(update_fields=["started_at", "ended_at", "value", "corrected_at", "version", "updated_at"])
    return row


@transaction.atomic
def undo_care_log(user, log_id):
    row = BabyCareLog.objects.select_for_update().select_related("baby__family").filter(pk=log_id).first()
    if not row:
        return False
    baby, _, access = _baby_for_user(user, row.baby_id, "care")
    if not access.can_log_care:
        raise PermissionDenied("Care logging is not permitted.")
    if row.created_by_id != user.id and row.created_at < timezone.now() - timedelta(minutes=10):
        raise PermissionDenied("Older entries from another caregiver cannot be undone.")
    row.delete()
    return True


def care_timeline(user, baby_id, *, start=None, end=None, limit=200):
    baby, _, _ = _baby_for_user(user, baby_id, "care")
    qs = BabyCareLog.objects.filter(baby=baby).select_related("created_by")
    if start:
        qs = qs.filter(started_at__gte=start)
    if end:
        qs = qs.filter(started_at__lte=end)
    return list(qs.order_by("-started_at", "-created_at")[: min(max(int(limit), 1), 500)])


def _sleep_overlap_seconds(row, start, end):
    if row.kind != BabyCareLog.Kind.SLEEP:
        return 0
    sleep_end = row.ended_at or end
    overlap_start = max(row.started_at, start)
    overlap_end = min(sleep_end, end)
    return max(0, (overlap_end - overlap_start).total_seconds())


def care_summary(user, baby_id, *, hours=24):
    baby, membership, _ = _baby_for_user(user, baby_id, "care")
    hours = min(max(int(hours), 1), 24 * 14)
    now = timezone.now()
    since = now - timedelta(hours=hours)
    rows = list(
        BabyCareLog.objects.filter(baby=baby)
        .filter(Q(started_at__gte=since) | Q(kind=BabyCareLog.Kind.SLEEP, ended_at__isnull=True))
        .filter(started_at__lte=now)
        .order_by("started_at")
    )
    counts = defaultdict(int)
    totals = defaultdict(float)
    last = {}
    sleep_seconds = 0
    active_sleep_started_at = None
    for row in rows:
        counts[row.kind] += 1
        last[row.kind] = row.started_at
        if row.kind in {BabyCareLog.Kind.BOTTLE, BabyCareLog.Kind.PUMP} and row.value.get("ml") is not None:
            totals[f"{row.kind}_ml"] += float(row.value["ml"])
        if row.kind == BabyCareLog.Kind.SLEEP:
            sleep_seconds += _sleep_overlap_seconds(row, since, now)
            if row.ended_at is None:
                active_sleep_started_at = row.started_at
    state, _ = BabyViewState.objects.get_or_create(baby=baby, membership=membership, defaults={"last_viewed_at": now})
    since_last = BabyCareLog.objects.filter(baby=baby, created_at__gt=state.last_viewed_at).count()
    return {
        "window_hours": hours,
        "counts": dict(counts),
        "totals": dict(totals),
        "sleep_minutes": round(sleep_seconds / 60),
        "active_sleep_started_at": active_sleep_started_at.isoformat() if active_sleep_started_at else None,
        "last": {key: value.isoformat() for key, value in last.items()},
        "new_since_last_view": since_last,
    }


def mark_viewed(user, baby_id):
    baby, membership, _ = _baby_for_user(user, baby_id, "care")
    state, _ = BabyViewState.objects.update_or_create(baby=baby, membership=membership, defaults={"last_viewed_at": timezone.now()})
    return state


def create_handover(user, baby_id, *, from_at, to_at, note=""):
    baby, _, access = _baby_for_user(user, baby_id, "care")
    if not access.can_log_care:
        raise PermissionDenied("Care handover is not permitted.")
    if to_at <= from_at:
        raise ValidationError({"to_at": "Handover end must be after start."})
    return CareHandoverNote.objects.create(family=baby.family, baby=baby, from_at=from_at, to_at=to_at, note=note, created_by=user)


def handover_payload(user, handover_id):
    handover = CareHandoverNote.objects.select_related("baby__family").filter(pk=handover_id).first()
    if not handover:
        raise ValidationError({"handover": "Handover not found."})
    baby, membership, _ = _baby_for_user(user, handover.baby_id, "care")
    rows = list(
        BabyCareLog.objects.filter(baby=baby)
        .filter(Q(started_at__gte=handover.from_at, started_at__lte=handover.to_at) | Q(kind=BabyCareLog.Kind.SLEEP, ended_at__isnull=True, started_at__lt=handover.from_at))
        .filter(started_at__lte=handover.to_at)
        .order_by("started_at")
    )
    HandoverRead.objects.update_or_create(handover=handover, membership=membership, defaults={"read_at": timezone.now()})
    counts = defaultdict(int)
    totals = defaultdict(float)
    sleep_seconds = 0
    for row in rows:
        counts[row.kind] += 1
        if row.kind in {BabyCareLog.Kind.BOTTLE, BabyCareLog.Kind.PUMP} and row.value.get("ml") is not None:
            totals[f"{row.kind}_ml"] += float(row.value["ml"])
        sleep_seconds += _sleep_overlap_seconds(row, handover.from_at, handover.to_at)
    return {
        "id": str(handover.id),
        "from_at": handover.from_at.isoformat(),
        "to_at": handover.to_at.isoformat(),
        "note": handover.note,
        "counts": dict(counts),
        "totals": dict(totals),
        "sleep_minutes": round(sleep_seconds / 60),
        "events": [
            {"id": row.id, "kind": row.kind, "started_at": row.started_at, "ended_at": row.ended_at, "value": row.value}
            for row in rows
        ],
    }
