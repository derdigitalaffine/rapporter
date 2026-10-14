from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from .models import FamilyEvent, Membership
from .scheduling_models import (
    SchedulingDependency,
    SchedulingOccurrenceOverride,
    SchedulingRuleVersion,
    SchedulingSeries,
    SchedulingTemplate,
)
from .scheduling_rules import normalize_scheduling_rule
from .unified_action_models import Action


SERIES_MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT}
INSTANCE_EDITOR_ROLES = {
    Membership.Role.OWNER,
    Membership.Role.ADULT,
    Membership.Role.TEEN,
    Membership.Role.CHILD,
}


def _membership(family, actor):
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Family membership is required.")
    membership = Membership.objects.filter(family=family, user=actor).first()
    if membership is None and not getattr(actor, "is_superuser", False):
        raise PermissionDenied("Family membership is required.")
    return membership


def _can_manage_series(series, actor):
    membership = _membership(series.family, actor)
    if getattr(actor, "is_superuser", False):
        return True
    if membership.role in SERIES_MANAGER_ROLES:
        return True
    return membership.role in INSTANCE_EDITOR_ROLES and series.created_by_id == actor.id


def _require_series_manager(series, actor):
    if not _can_manage_series(series, actor):
        raise PermissionDenied("Only the series creator or an adult family manager may change this series.")


def _require_instance_editor(series, actor):
    membership = _membership(series.family, actor)
    if getattr(actor, "is_superuser", False):
        return
    if membership.role not in INSTANCE_EDITOR_ROLES:
        raise PermissionDenied("This membership cannot change individual occurrences.")


def _resolve_target(target_type, target_id):
    if target_type == SchedulingSeries.TargetType.EVENT:
        return FamilyEvent.objects.select_related("family").filter(id=target_id).first()
    if target_type == SchedulingSeries.TargetType.ACTION:
        return Action.objects.select_related("family").filter(id=target_id).first()
    raise ValidationError({"target_type": "Unsupported scheduling target type."})


def _normalize_for_family(family, rule):
    try:
        return normalize_scheduling_rule(rule, family.timezone)
    except ValueError as exc:
        raise ValidationError({"rule": str(exc)}) from exc


@transaction.atomic
def create_series(*, target_type, target_id, rule, actor):
    """Create scheduling metadata around an existing canonical object."""
    target = _resolve_target(target_type, target_id)
    if target is None:
        raise ValidationError({"target_id": "Scheduling target does not exist."})
    membership = _membership(target.family, actor)
    if not getattr(actor, "is_superuser", False) and membership.role not in INSTANCE_EDITOR_ROLES:
        raise PermissionDenied("This membership cannot create a recurring series.")
    normalized = _normalize_for_family(target.family, rule)
    try:
        series = SchedulingSeries.objects.create(
            family=target.family,
            target_type=target_type,
            target_id=target.id,
            current_version=1,
            created_by=actor,
        )
    except IntegrityError as exc:
        raise ValidationError("Scheduling metadata already exists for this object.") from exc
    SchedulingRuleVersion.objects.create(
        series=series,
        version=1,
        rule=normalized,
        change_scope=SchedulingRuleVersion.ChangeScope.INITIAL,
        created_by=actor,
    )
    return series


@transaction.atomic
def append_rule_version(*, series, rule, actor, scope, effective_from=None):
    """Append a rule version; old versions are never updated or deleted."""
    locked = SchedulingSeries.objects.select_for_update().select_related("family").get(pk=series.pk)
    _require_series_manager(locked, actor)
    if scope not in {SchedulingRuleVersion.ChangeScope.WHOLE, SchedulingRuleVersion.ChangeScope.FUTURE}:
        raise ValidationError({"scope": "Rule edits must target the whole series or this-and-future."})
    if scope == SchedulingRuleVersion.ChangeScope.FUTURE:
        if effective_from is None:
            raise ValidationError({"effective_from": "This-and-future edits require an effective date."})
        if isinstance(effective_from, str):
            try:
                effective_from = date.fromisoformat(effective_from)
            except ValueError as exc:
                raise ValidationError({"effective_from": "Expected an ISO date."}) from exc
    elif effective_from is not None:
        raise ValidationError({"effective_from": "Whole-series edits do not take an effective date."})

    normalized = _normalize_for_family(locked.family, rule)
    version_number = locked.current_version + 1
    version = SchedulingRuleVersion.objects.create(
        series=locked,
        version=version_number,
        rule=normalized,
        change_scope=scope,
        effective_from=effective_from,
        created_by=actor,
    )
    locked.current_version = version_number
    locked.save(update_fields=["current_version", "updated_at"])
    return version


def rule_version_for_occurrence(series, occurrence_date):
    """Resolve the immutable rule version for a projected occurrence date.

    A whole-series edit resets the baseline for projections. Later future splits
    are then considered from that baseline onward. Already materialized/history
    objects are intentionally not rewritten by this resolver.
    """
    if isinstance(occurrence_date, str):
        occurrence_date = date.fromisoformat(occurrence_date)
    versions = list(series.rule_versions.order_by("version"))
    if not versions:
        raise ValidationError("Scheduling series has no rule version.")
    baselines = [item for item in versions if item.change_scope in {SchedulingRuleVersion.ChangeScope.INITIAL, SchedulingRuleVersion.ChangeScope.WHOLE}]
    baseline = max(baselines, key=lambda item: item.version)
    candidates = [
        item
        for item in versions
        if item.version > baseline.version
        and item.change_scope == SchedulingRuleVersion.ChangeScope.FUTURE
        and item.effective_from <= occurrence_date
    ]
    if not candidates:
        return baseline
    return max(candidates, key=lambda item: (item.effective_from, item.version))


@transaction.atomic
def record_occurrence_override(
    *,
    series,
    occurrence_key,
    kind,
    actor,
    payload=None,
    detached_fields=None,
):
    """Persist a one-occurrence skip/override/detach without changing the series."""
    locked = SchedulingSeries.objects.select_for_update().get(pk=series.pk)
    _require_instance_editor(locked, actor)
    occurrence_key = str(occurrence_key or "").strip()
    if not occurrence_key or len(occurrence_key) > 96:
        raise ValidationError({"occurrence_key": "A stable occurrence key is required."})
    if kind not in SchedulingOccurrenceOverride.Kind.values:
        raise ValidationError({"kind": "Unsupported occurrence override kind."})
    payload = payload or {}
    detached_fields = detached_fields or []
    if not isinstance(payload, dict):
        raise ValidationError({"payload": "Occurrence override payload must be an object."})
    if not isinstance(detached_fields, list) or any(not isinstance(item, str) or not item for item in detached_fields):
        raise ValidationError({"detached_fields": "Detached fields must be a list of field names."})
    detached_fields = sorted(set(detached_fields))
    override, _ = SchedulingOccurrenceOverride.objects.update_or_create(
        series=locked,
        occurrence_key=occurrence_key,
        defaults={
            "kind": kind,
            "payload": payload,
            "detached_fields": detached_fields,
            "rule_version": locked.current_version,
            "created_by": actor,
        },
    )
    return override


@transaction.atomic
def create_dependency(
    *,
    family,
    anchor_type,
    anchor_id,
    output_type,
    relative_rule,
    actor,
    anchor_scope=SchedulingDependency.AnchorScope.SERIES,
    anchor_occurrence_key="",
    output_blueprint=None,
    inheritance=None,
    conflict_policy=None,
):
    """Persist a dependency edge. Relative-rule execution is added in slice 3."""
    membership = _membership(family, actor)
    if not getattr(actor, "is_superuser", False) and membership.role not in INSTANCE_EDITOR_ROLES:
        raise PermissionDenied("This membership cannot create scheduling dependencies.")
    if anchor_type not in {SchedulingSeries.TargetType.EVENT, SchedulingSeries.TargetType.ACTION}:
        raise ValidationError({"anchor_type": "Unsupported dependency anchor type."})
    anchor = _resolve_target(anchor_type, anchor_id)
    if anchor is None or anchor.family_id != family.id:
        raise ValidationError({"anchor_id": "Dependency anchor does not belong to this family."})
    if output_type not in SchedulingDependency.OutputType.values:
        raise ValidationError({"output_type": "Unsupported dependency output type."})
    if anchor_scope not in SchedulingDependency.AnchorScope.values:
        raise ValidationError({"anchor_scope": "Unsupported dependency anchor scope."})
    anchor_occurrence_key = str(anchor_occurrence_key or "").strip()
    if anchor_scope == SchedulingDependency.AnchorScope.OCCURRENCE and not anchor_occurrence_key:
        raise ValidationError({"anchor_occurrence_key": "Occurrence dependencies require an occurrence key."})
    if anchor_scope == SchedulingDependency.AnchorScope.SERIES:
        anchor_occurrence_key = ""
    if not isinstance(relative_rule, dict) or not relative_rule:
        raise ValidationError({"relative_rule": "Relative rule must be a non-empty object."})
    for field_name, value in {
        "output_blueprint": output_blueprint or {},
        "inheritance": inheritance or {},
        "conflict_policy": conflict_policy or {},
    }.items():
        if not isinstance(value, dict):
            raise ValidationError({field_name: "Expected an object."})
    return SchedulingDependency.objects.create(
        family=family,
        anchor_type=anchor_type,
        anchor_id=anchor.id,
        anchor_scope=anchor_scope,
        anchor_occurrence_key=anchor_occurrence_key,
        output_type=output_type,
        output_blueprint=output_blueprint or {},
        relative_rule=relative_rule,
        inheritance=inheritance or {},
        conflict_policy=conflict_policy or {},
        created_by=actor,
    )


@transaction.atomic
def create_template(*, family, name, rule, actor, scope=SchedulingTemplate.Scope.PERSONAL, dependency_blueprint=None, locked=False):
    membership = _membership(family, actor)
    name = str(name or "").strip()
    if not name:
        raise ValidationError({"name": "Template name is required."})
    if scope not in SchedulingTemplate.Scope.values:
        raise ValidationError({"scope": "Unsupported template scope."})
    if scope in {SchedulingTemplate.Scope.FAMILY, SchedulingTemplate.Scope.ADMIN}:
        if not getattr(actor, "is_superuser", False) and membership.role not in SERIES_MANAGER_ROLES:
            raise PermissionDenied("Only adult family managers may create shared scheduling templates.")
        owner = None
    else:
        if not getattr(actor, "is_superuser", False) and membership.role == Membership.Role.GUEST:
            raise PermissionDenied("Guest memberships cannot create scheduling templates.")
        owner = actor
    normalized = _normalize_for_family(family, rule)
    dependency_blueprint = dependency_blueprint or {}
    if not isinstance(dependency_blueprint, dict):
        raise ValidationError({"dependency_blueprint": "Expected an object."})
    return SchedulingTemplate.objects.create(
        family=family,
        owner=owner,
        scope=scope,
        name=name,
        rule=normalized,
        dependency_blueprint=dependency_blueprint,
        locked=bool(locked),
        created_by=actor,
    )
