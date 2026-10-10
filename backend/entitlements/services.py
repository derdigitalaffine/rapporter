import json
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from family.models import Family, Membership

from .catalog import FULL_ACCESS_PLAN_KEYS, VALID_PLAN_KEYS
from .models import CapabilityDefinition, EntitlementGrant, EntitlementGrantAudit


MAX_CAPABILITIES_PER_GRANT = 64
MAX_METADATA_BYTES = 4096
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

    def as_dict(self):
        return {
            "tier": self.tier,
            "display_name": self.display_name,
            "capabilities": list(self.capabilities),
            "origin_summary": self.origin_summary,
            "origins": list(self.origins),
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


def resolve_entitlements(family, *, at=None):
    """Resolve licensing only; module activation remains a separate product state."""
    at = at or timezone.now()
    definitions = _definitions()
    capabilities = {key for key, definition in definitions.items() if definition.default_light}
    grants = _active_grants(family, at)

    for grant in grants:
        if grant.plan_key in FULL_ACCESS_PLAN_KEYS:
            capabilities.update(definitions)
        for key in grant.capability_set or []:
            if key in definitions:
                capabilities.add(key)

    origins = tuple(sorted({grant.origin for grant in grants}, key=lambda value: (ORIGIN_ORDER.get(value, 99), value)))
    if not origins:
        origin_summary = "default_light"
    else:
        origin_summary = origins[0]

    premium_keys = {key for key, definition in definitions.items() if definition.premium}
    if any(grant.plan_key == "vip" for grant in grants):
        tier = "vip"
        display_name = "VIP"
    elif premium_keys.intersection(capabilities):
        tier = "premium"
        display_name = "Premium"
    else:
        tier = "light"
        display_name = "Light"

    return EntitlementSnapshot(
        tier=tier,
        display_name=display_name,
        capabilities=tuple(sorted(capabilities)),
        origin_summary=origin_summary,
        origins=origins,
    )


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
    return grant
