from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .action_schedule import WEEKDAYS, local_datetime
from .models import FamilyEvent, Membership
from .scheduling_models import SchedulingDependency, SchedulingMaterialization, SchedulingSeries
from .scheduling_relative import (
    apply_relative_rule,
    describe_relative_rule,
    materialize_dependency,
    normalize_dependency_blueprint,
    normalize_inheritance,
    normalize_relative_rule,
)
from .scheduling_rules import from_action_schedule, from_event_recurrence, preview_occurrence_dates
from .scheduling_series import create_dependency
from .unified_action_models import Action


MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT}
HORIZON_DAYS = 120
MAX_OCCURRENCES = 32


def _membership(family, actor):
    membership = Membership.objects.filter(family=family, user=actor).first()
    if membership is None and not getattr(actor, "is_superuser", False):
        raise PermissionDenied("Family membership is required.")
    return membership


def _anchor(anchor_type, anchor_id, family):
    if anchor_type == SchedulingSeries.TargetType.EVENT:
        anchor = FamilyEvent.objects.filter(family=family, id=anchor_id).first()
    elif anchor_type == SchedulingSeries.TargetType.ACTION:
        anchor = Action.objects.filter(family=family, id=anchor_id).first()
    else:
        anchor = None
    if anchor is None:
        raise ValidationError({"anchor_id": "Scheduling anchor is not available."})
    return anchor


def _clock_for_action(action, day, zone):
    if action.due_at:
        return action.due_at.astimezone(zone).time().replace(tzinfo=None)
    for segment in (action.schedule or {}).get("segments", []):
        if WEEKDAYS[day.weekday()] in segment.get("weekdays", WEEKDAYS):
            raw = segment.get("preferred_time") or (segment.get("window") or {}).get("end")
            if raw:
                return time.fromisoformat(raw)
    return time(9, 0)


def anchor_occurrences(anchor_type, anchor, family_timezone, *, after=None, limit=5):
    zone = ZoneInfo(family_timezone or "UTC")
    after = after or timezone.now()
    if after.tzinfo is None:
        after = after.replace(tzinfo=zone)
    if anchor_type == SchedulingSeries.TargetType.EVENT:
        if not anchor.starts_at:
            return []
        recurrence = (anchor.payload or {}).get("recurrence") if isinstance(anchor.payload, dict) else None
        if not recurrence:
            return [(anchor.starts_at.isoformat(), anchor.starts_at)] if anchor.starts_at >= after else []
        rule = from_event_recurrence(recurrence, anchor.starts_at, family_timezone)
        dates = preview_occurrence_dates(rule, family_timezone, after=after.astimezone(zone).date(), limit=limit)
        clock = anchor.starts_at.astimezone(zone).time().replace(tzinfo=None)
        return [(value, local_datetime(date.fromisoformat(value), clock, zone)) for value in dates]

    schedule = anchor.schedule or {}
    recurrence = schedule.get("recurrence")
    if not recurrence:
        return [(anchor.due_at.isoformat(), anchor.due_at)] if anchor.due_at and anchor.due_at >= after else []
    if schedule.get("mode", "static") != "static":
        if anchor.due_at and anchor.due_at >= after:
            return [(anchor.due_at.isoformat(), anchor.due_at)]
        return []
    rule = from_action_schedule(schedule, family_timezone)
    dates = preview_occurrence_dates(rule, family_timezone, after=after.astimezone(zone).date(), limit=limit)
    result = []
    for value in dates:
        day = date.fromisoformat(value)
        result.append((value, local_datetime(day, _clock_for_action(anchor, day, zone), zone)))
    return result


def dependency_payload(dependency, *, language="de"):
    return {
        "id": str(dependency.id),
        "anchor_type": dependency.anchor_type,
        "anchor_id": str(dependency.anchor_id),
        "anchor_scope": dependency.anchor_scope,
        "anchor_occurrence_key": dependency.anchor_occurrence_key,
        "output_type": dependency.output_type,
        "output_blueprint": dependency.output_blueprint,
        "relative_rule": dependency.relative_rule,
        "relative_summary": describe_relative_rule(dependency.relative_rule, language),
        "inheritance": dependency.inheritance,
        "conflict_policy": dependency.conflict_policy,
        "enabled": dependency.enabled,
    }


def preview_relative_dependency(*, family, anchor_type, anchor_id, relative_rule, output_type, output_blueprint=None, inheritance=None, language="de", limit=5):
    anchor = _anchor(anchor_type, anchor_id, family)
    rule = normalize_relative_rule(relative_rule)
    blueprint = normalize_dependency_blueprint(output_type, output_blueprint)
    inheritance = normalize_inheritance(inheritance)
    rows = []
    for key, anchor_at in anchor_occurrences(anchor_type, anchor, family.timezone, limit=limit):
        scheduled = apply_relative_rule(anchor_at, rule, family.timezone)
        if scheduled is None:
            continue
        rows.append({"anchor_occurrence_key": key, "anchor_at": anchor_at.isoformat(), "scheduled_for": scheduled.isoformat()})
    return {
        "relative_rule": rule,
        "summary": describe_relative_rule(rule, language),
        "output_type": output_type,
        "output_blueprint": blueprint,
        "inheritance": inheritance,
        "occurrences": rows,
    }


@transaction.atomic
def create_relative_dependency(*, family, anchor_type, anchor_id, output_type, relative_rule, actor, anchor_scope=SchedulingDependency.AnchorScope.SERIES, anchor_occurrence_key="", output_blueprint=None, inheritance=None, conflict_policy=None):
    _membership(family, actor)
    rule = normalize_relative_rule(relative_rule)
    blueprint = normalize_dependency_blueprint(output_type, output_blueprint)
    inheritance = normalize_inheritance(inheritance)
    dependency = create_dependency(
        family=family,
        anchor_type=anchor_type,
        anchor_id=anchor_id,
        output_type=output_type,
        relative_rule=rule,
        actor=actor,
        anchor_scope=anchor_scope,
        anchor_occurrence_key=anchor_occurrence_key,
        output_blueprint=blueprint,
        inheritance=inheritance,
        conflict_policy=conflict_policy or {},
    )
    refresh_dependency(dependency)
    return dependency


@transaction.atomic
def update_relative_dependency(dependency, *, actor, changes):
    membership = _membership(dependency.family, actor)
    if not getattr(actor, "is_superuser", False) and membership.role not in MANAGER_ROLES and dependency.created_by_id != actor.id:
        raise PermissionDenied("Only the creator or an adult family manager may change this dependency.")
    allowed = {"relative_rule", "output_blueprint", "inheritance", "conflict_policy", "enabled"}
    if set(changes) - allowed:
        raise ValidationError("Unsupported dependency fields.")
    if "relative_rule" in changes:
        dependency.relative_rule = normalize_relative_rule(changes["relative_rule"])
    if "output_blueprint" in changes:
        dependency.output_blueprint = normalize_dependency_blueprint(dependency.output_type, changes["output_blueprint"])
    if "inheritance" in changes:
        dependency.inheritance = normalize_inheritance(changes["inheritance"])
    if "conflict_policy" in changes:
        if not isinstance(changes["conflict_policy"], dict):
            raise ValidationError({"conflict_policy": "Expected an object."})
        dependency.conflict_policy = changes["conflict_policy"]
    if "enabled" in changes:
        if type(changes["enabled"]) is not bool:
            raise ValidationError({"enabled": "Expected boolean."})
        dependency.enabled = changes["enabled"]
    dependency.save(update_fields=[*changes.keys(), "updated_at"])
    if dependency.enabled:
        refresh_dependency(dependency)
    return dependency


def refresh_dependency(dependency, *, horizon_days=HORIZON_DAYS):
    if not dependency.enabled:
        return []
    anchor = _anchor(dependency.anchor_type, dependency.anchor_id, dependency.family)
    after = timezone.now() - timedelta(minutes=1)
    limit = MAX_OCCURRENCES
    materialized = []
    for key, anchor_at in anchor_occurrences(dependency.anchor_type, anchor, dependency.family.timezone, after=after, limit=limit):
        if anchor_at > timezone.now() + timedelta(days=horizon_days):
            break
        if dependency.anchor_scope == SchedulingDependency.AnchorScope.OCCURRENCE and key != dependency.anchor_occurrence_key:
            continue
        row = materialize_dependency(dependency, anchor, anchor_at, key)
        if row:
            materialized.append(row)
    return materialized


def refresh_anchor_dependencies(family, anchor_type, anchor_id):
    rows = SchedulingDependency.objects.filter(family=family, anchor_type=anchor_type, anchor_id=anchor_id, enabled=True)
    result = []
    for dependency in rows:
        result.extend(refresh_dependency(dependency))
    return result


def materialization_payload(row):
    return {
        "id": str(row.id),
        "dependency_id": str(row.dependency_id),
        "anchor_occurrence_key": row.anchor_occurrence_key,
        "output_type": row.output_type,
        "output_id": str(row.output_id) if row.output_id else None,
        "scheduled_for": row.scheduled_for.isoformat(),
        "status": row.status,
        "projected_payload": row.projected_payload,
        "detached_fields": (row.provenance or {}).get("detached_fields", []),
    }
