import json
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from family.models import Family, Membership
from telemetry.service import try_record_audit_event

from .catalog import COMMERCIAL_CUTOVER_KEY, FULL_ACCESS_PLAN_KEYS, LEGACY_SOURCE_REF, VALID_PLAN_KEYS
from .models import CapabilityDefinition, EntitlementCutover, EntitlementGrant, EntitlementGrantAudit


MAX_CAPABILITIES_PER_GRANT = 64
MAX_METADATA_BYTES = 4096
PRE_COMMERCIAL_ORIGIN_SUMMARY = "pre_commercial_vip"
ADMIN_TIER_OVERRIDE_MODE = "tier_override"
ORIGIN_ORDER = {
    EntitlementGrant.Origin.LEGACY_GRANDFATHERED: 0,
    EntitlementGrant.Origin.PURCHASED_LIFETIME: 1,
    EntitlementGrant.Origin.ADMIN_GRANT: 2,
    EntitlementGrant.Origin.SUBSCRIPTION: 3,
    EntitlementGrant.Origin.PROMOTION: 4,
}


@dataclass(frozen=True)
class EntitlementSnapshot:
    tier: str
    display_name: str
    capabilities: tuple[str, ...]
    origin_summary: str
    origins: tuple[str, ...]
    override_tier: str | None = None
    override_ends_at: object | None = None

    def as_dict(self):
        return {
            "tier": self.tier,
            "display_name": self.display_name,
            "capabilities": list(self.capabilities),
            "origin_summary": self.origin_summary,
            "origins": list(self.origins),
            "override_tier": self.override_tier,
            "override_ends_at": self.override_ends_at.isoformat() if self.override_ends_at else None,
        }


def _definitions():
    rows = CapabilityDefinition.objects.filter(deprecated=False).order_by("key")
    return {row.key: row for row in rows}


def _active_grants(family, at):
    return list(
        EntitlementGrant.objects.filter(
            family=family,
            active=True,
            revoked_at__isnull=True,
        )
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=at))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=at))
        .order_by("created_at", "id")
    )


def _is_tier_override(grant):
    return grant.origin == EntitlementGrant.Origin.ADMIN_GRANT and (grant.metadata or {}).get("mode") == ADMIN_TIER_OVERRIDE_MODE


def _active_tier_override(grants):
    matches = [grant for grant in grants if _is_tier_override(grant) and grant.plan_key in VALID_PLAN_KEYS]
    return matches[-1] if matches else None


def _capabilities_for_tier(definitions, tier):
    if tier == "light":
        return {key for key, definition in definitions.items() if definition.default_light}
    if tier in FULL_ACCESS_PLAN_KEYS:
        return set(definitions)
    return set()


def _snapshot_from(definitions, pre_commercial_vip, grants):
    override = _active_tier_override(grants)
    if override is not None:
        capabilities = _capabilities_for_tier(definitions, override.plan_key)
        tier = override.plan_key
        display_name = "VIP" if tier == "vip" else tier.capitalize()
    else:
        capabilities = (
            set(definitions)
            if pre_commercial_vip
            else {key for key, definition in definitions.items() if definition.default_light}
        )
        for grant in grants:
            if grant.plan_key in FULL_ACCESS_PLAN_KEYS:
                capabilities.update(definitions)
            for key in grant.capability_set or []:
                if key in definitions:
                    capabilities.add(key)

        premium_keys = {key for key, definition in definitions.items() if definition.premium}
        if pre_commercial_vip or any(grant.plan_key == "vip" for grant in grants):
            tier = "vip"
            display_name = "VIP"
        elif premium_keys.intersection(capabilities):
            tier = "premium"
            display_name = "Premium"
        else:
            tier = "light"
            display_name = "Light"

    origins = tuple(sorted({grant.origin for grant in grants}, key=lambda value: (ORIGIN_ORDER.get(value, 99), value)))
    if override is not None:
        origin_summary = EntitlementGrant.Origin.ADMIN_GRANT
    elif pre_commercial_vip:
        origin_summary = PRE_COMMERCIAL_ORIGIN_SUMMARY
    elif not origins:
        origin_summary = "default_light"
    else:
        origin_summary = origins[0]

    return EntitlementSnapshot(
        tier=tier,
        display_name=display_name,
        capabilities=tuple(sorted(capabilities)),
        origin_summary=origin_summary,
        origins=origins,
        override_tier=override.plan_key if override else None,
        override_ends_at=override.ends_at if override else None,
    )


def resolve_entitlements(family, *, at=None):
    """Resolve licensing only; module activation remains a separate product state.

    Before the explicit commercial cutover all families intentionally receive the
    full VIP capability set. The cutover marker is the single switch that hands
    access control back to persisted grants/default Light capabilities. Existing
    families are grandfathered by ``apply_commercial_cutover`` at that boundary,
    while families created afterwards can follow future commercial policy without
    another resolver special case.

    Explicit Superadmin tier overrides are the only layer allowed to replace the
    otherwise additive result. They never mutate or delete the underlying billing,
    legacy or purchased grants, so expiry/revocation automatically reveals the
    next valid canonical state without a data migration.
    """
    at = at or timezone.now()
    definitions = _definitions()
    pre_commercial_vip = not EntitlementCutover.objects.filter(pk=COMMERCIAL_CUTOVER_KEY).exists()
    return _snapshot_from(definitions, pre_commercial_vip, _active_grants(family, at))


def resolve_entitlements_for_families(families, *, at=None):
    """Resolve many families with a constant entitlement query count.

    This preserves the exact single-family resolver semantics while loading the
    capability catalog, commercial-cutover marker and all active grants only once.
    The returned mapping is keyed by family primary key.
    """
    family_list = list(families)
    if not family_list:
        return {}
    at = at or timezone.now()
    definitions = _definitions()
    pre_commercial_vip = not EntitlementCutover.objects.filter(pk=COMMERCIAL_CUTOVER_KEY).exists()
    grants = list(
        EntitlementGrant.objects.filter(
            family_id__in=[family.pk for family in family_list],
            active=True,
            revoked_at__isnull=True,
        )
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=at))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=at))
        .order_by("family_id", "created_at", "id")
    )
    grants_by_family = {}
    for grant in grants:
        grants_by_family.setdefault(grant.family_id, []).append(grant)
    return {
        family.pk: _snapshot_from(definitions, pre_commercial_vip, grants_by_family.get(family.pk, ()))
        for family in family_list
    }


def has_capability(family, capability_key, *, at=None):
    if not CapabilityDefinition.objects.filter(key=capability_key, deprecated=False).exists():
        return False
    return capability_key in resolve_entitlements(family, at=at).capabilities


def require_capability(user, family, capability_key, *, at=None):
    """Server-side gate: tenant access is checked before entitlement state."""
    if family.status != Family.Status.ACTIVE or not Membership.objects.filter(family=family, user=user).exists():
        raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
    if not has_capability(family, capability_key, at=at):
        raise PermissionDenied("Funktion ist für diese Familie nicht freigeschaltet.")
    return True


def _normalise_capabilities(capability_set):
    values = list(dict.fromkeys(capability_set or []))
    if len(values) > MAX_CAPABILITIES_PER_GRANT:
        raise ValidationError("Zu viele Capabilities in einem Grant.")
    known = set(CapabilityDefinition.objects.filter(key__in=values, deprecated=False).values_list("key", flat=True))
    unknown = sorted(set(values) - known)
    if unknown:
        raise ValidationError(f"Unbekannte Capability: {unknown[0]}")
    return sorted(values)


def _normalise_metadata(metadata):
    metadata = metadata or {}
    if not isinstance(metadata, dict):
        raise ValidationError("Grant-Metadaten müssen ein Objekt sein.")
    encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValidationError("Grant-Metadaten sind zu groß.")
    return metadata


def _validate_plan(plan_key):
    plan_key = (plan_key or "").strip()
    if plan_key and plan_key not in VALID_PLAN_KEYS:
        raise ValidationError("Unbekannter Plan-Key.")
    return plan_key


def _audit_snapshot(grant):
    return {
        "origin": grant.origin,
        "plan_key": grant.plan_key,
        "capability_set": sorted(grant.capability_set or []),
        "active": grant.active,
        "starts_at": grant.starts_at.isoformat() if grant.starts_at else None,
        "ends_at": grant.ends_at.isoformat() if grant.ends_at else None,
        "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
    }


def _record_entitlement_audit_event(event_key, *, grant, family, actor=None):
    is_admin_action = actor is not None
    try_record_audit_event(
        event_key,
        actor=actor,
        actor_class="superadmin" if is_admin_action else "system",
        family=family,
        outcome="success",
        reason="admin_action" if is_admin_action else "system",
        target_type="entitlement",
        target_id=str(grant.pk),
        metadata={"origin": grant.origin},
    )


@transaction.atomic
def apply_commercial_cutover(*, cutover_at):
    """Grandfather every family that existed at an explicit commercial cutover instant."""
    if cutover_at is None or timezone.is_naive(cutover_at):
        raise ValidationError("Commercial-Cutover benötigt einen timezone-aware Zeitstempel.")
    now = timezone.now()
    if cutover_at > now:
        raise ValidationError("Commercial-Cutover darf nicht in der Zukunft liegen.")

    marker = EntitlementCutover.objects.select_for_update().filter(pk=COMMERCIAL_CUTOVER_KEY).first()
    if marker is not None and marker.cutover_at != cutover_at:
        raise ValidationError("Commercial-Cutover wurde bereits mit einem anderen Stichtag angewendet.")
    if marker is None:
        marker = EntitlementCutover.objects.create(
            key=COMMERCIAL_CUTOVER_KEY,
            cutover_at=cutover_at,
            applied_at=now,
            eligible_family_count=0,
        )

    eligible = Family.objects.filter(created_at__lte=cutover_at).order_by("id").only("id")
    eligible_count = eligible.count()
    created_count = 0
    reason = "Bestandsfamilie beim Commercial-Cutover"
    for family in eligible.iterator(chunk_size=500):
        grant, created = EntitlementGrant.objects.get_or_create(
            family=family,
            origin=EntitlementGrant.Origin.LEGACY_GRANDFATHERED,
            source_ref=LEGACY_SOURCE_REF,
            defaults={
                "plan_key": "vip",
                "capability_set": [],
                "starts_at": cutover_at,
                "active": True,
                "reason": reason,
                "metadata": {
                    "cutover_key": COMMERCIAL_CUTOVER_KEY,
                    "cutover_at": cutover_at.isoformat(),
                },
            },
        )
        if created:
            created_count += 1
            EntitlementGrantAudit.objects.create(
                grant=grant,
                family=family,
                action=EntitlementGrantAudit.Action.GRANTED,
                actor=None,
                reason=reason,
                snapshot=_audit_snapshot(grant),
            )
            _record_entitlement_audit_event(
                "entitlement.granted",
                grant=grant,
                family=family,
            )

    if marker.eligible_family_count != eligible_count:
        marker.eligible_family_count = eligible_count
        marker.save(update_fields=["eligible_family_count", "updated_at"])
    return marker, created_count


@transaction.atomic
def create_admin_grant(
    *,
    actor,
    family,
    plan_key="",
    capability_set=None,
    starts_at=None,
    ends_at=None,
    reason,
    metadata=None,
):
    if not getattr(actor, "is_superuser", False):
        raise PermissionDenied("Administrative Grants erfordern Superadmin-Rechte.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Ein auditierbarer Grund ist erforderlich.")
    plan_key = _validate_plan(plan_key)
    capability_set = _normalise_capabilities(capability_set)
    metadata = _normalise_metadata(metadata)
    if not plan_key and not capability_set:
        raise ValidationError("Grant benötigt Plan oder Capability.")
    if starts_at and ends_at and ends_at <= starts_at:
        raise ValidationError("Grant-Ende muss nach dem Start liegen.")

    grant = EntitlementGrant.objects.create(
        family=family,
        origin=EntitlementGrant.Origin.ADMIN_GRANT,
        plan_key=plan_key,
        capability_set=capability_set,
        starts_at=starts_at,
        ends_at=ends_at,
        active=True,
        metadata=metadata,
        created_by=actor,
        reason=reason[:500],
    )
    EntitlementGrantAudit.objects.create(
        grant=grant,
        family=family,
        action=EntitlementGrantAudit.Action.GRANTED,
        actor=actor,
        reason=reason[:500],
        snapshot=_audit_snapshot(grant),
    )
    _record_entitlement_audit_event(
        "entitlement.granted",
        grant=grant,
        family=family,
        actor=actor,
    )
    return grant


@transaction.atomic
def revoke_admin_grant(*, actor, grant, reason):
    if not getattr(actor, "is_superuser", False):
        raise PermissionDenied("Administrative Grants erfordern Superadmin-Rechte.")
    if grant.origin != EntitlementGrant.Origin.ADMIN_GRANT:
        raise ValidationError("Dieser Service widerruft nur administrative Grants.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Ein auditierbarer Grund ist erforderlich.")

    grant = EntitlementGrant.objects.select_for_update().get(pk=grant.pk)
    if grant.revoked_at:
        return grant
    grant.active = False
    grant.revoked_at = timezone.now()
    grant.save(update_fields=["active", "revoked_at"])
    EntitlementGrantAudit.objects.create(
        grant=grant,
        family=grant.family,
        action=EntitlementGrantAudit.Action.REVOKED,
        actor=actor,
        reason=reason[:500],
        snapshot=_audit_snapshot(grant),
    )
    _record_entitlement_audit_event(
        "entitlement.revoked",
        grant=grant,
        family=grant.family,
        actor=actor,
    )
    return grant


def active_admin_tier_overrides(family, *, at=None):
    at = at or timezone.now()
    return [grant for grant in _active_grants(family, at) if _is_tier_override(grant)]


@transaction.atomic
def set_admin_tier_override(*, actor, family, tier, reason, ends_at=None):
    if not getattr(actor, "is_superuser", False):
        raise PermissionDenied("Lizenz-Overrides erfordern Superadmin-Rechte.")
    tier = _validate_plan(tier)
    if not tier:
        raise ValidationError("Ein Ziel-Tier ist erforderlich.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Ein auditierbarer Grund ist erforderlich.")
    now = timezone.now()
    if ends_at is not None:
        if timezone.is_naive(ends_at):
            raise ValidationError("Override-Ende benötigt einen timezone-aware Zeitstempel.")
        if ends_at <= now:
            raise ValidationError("Override-Ende muss in der Zukunft liegen.")

    current = list(
        EntitlementGrant.objects.select_for_update().filter(
            family=family,
            origin=EntitlementGrant.Origin.ADMIN_GRANT,
            active=True,
            revoked_at__isnull=True,
        ).order_by("created_at", "id")
    )
    for grant in current:
        if _is_tier_override(grant):
            revoke_admin_grant(actor=actor, grant=grant, reason=f"Durch neuen Tier-Override ersetzt: {reason}")

    return create_admin_grant(
        actor=actor,
        family=family,
        plan_key=tier,
        starts_at=now,
        ends_at=ends_at,
        reason=reason,
        metadata={"mode": ADMIN_TIER_OVERRIDE_MODE},
    )


@transaction.atomic
def clear_admin_tier_override(*, actor, family, reason):
    if not getattr(actor, "is_superuser", False):
        raise PermissionDenied("Lizenz-Overrides erfordern Superadmin-Rechte.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Ein auditierbarer Grund ist erforderlich.")
    current = list(
        EntitlementGrant.objects.select_for_update().filter(
            family=family,
            origin=EntitlementGrant.Origin.ADMIN_GRANT,
            active=True,
            revoked_at__isnull=True,
        ).order_by("created_at", "id")
    )
    revoked = []
    for grant in current:
        if _is_tier_override(grant):
            revoked.append(revoke_admin_grant(actor=actor, grant=grant, reason=reason))
    return revoked
