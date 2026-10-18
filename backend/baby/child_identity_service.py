from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from auth_identity.service import (
    EmailConflictError,
    EmailIdentityError,
    pending_identity,
    primary_identity,
    queue_verification,
    request_pending_email,
)
from family.family_relationship_models import FamilyRelationship
from family.models import Membership, UserProfile

from .family_modules import MANAGER_ROLES, active_membership, care_access, require_module
from .models import BabyProfile, CareCircleAccess, ManagedChildGuardian


User = get_user_model()


def child_profile(baby_id, *, for_update=False):
    queryset = BabyProfile.objects.select_related("family", "membership__user")
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    baby = queryset.filter(pk=baby_id).first()
    if not baby:
        raise NotFound("Child identity not found.")
    return baby


def _bootstrap_guardian_allowed(membership, baby):
    return CareCircleAccess.objects.filter(
        family=baby.family,
        membership=membership,
        baby__isnull=True,
        is_guardian=True,
    ).exists()


def membership_has_child_custody(membership, child):
    """Read existing custody directly, including identities predating BabyProfile."""
    if (membership.family_id != child.family_id or membership.role not in MANAGER_ROLES
            or child.role != Membership.Role.CHILD or child.family.status != "active"):
        return False
    return FamilyRelationship.objects.filter(
        family_id=child.family_id, child_membership=child,
        related_membership=membership, has_custody=True,
        status=FamilyRelationship.Status.ACTIVE,
    ).exists()


def _custody_guardian_allowed(membership, baby):
    return bool(baby.membership_id and membership_has_child_custody(membership, baby.membership))


def require_child_membership_guardian(user, child, *, manage=False):
    """Canonical authority for membership-based consumers; no backfill needed."""
    membership = active_membership(user, child.family)
    if membership_has_child_custody(membership, child):
        return membership, _custody_authority(membership)
    baby = BabyProfile.objects.filter(family=child.family, membership=child).first()
    if baby:
        return require_child_guardian(user, baby, manage=manage)
    raise PermissionDenied("Sorgerecht oder eine bestehende Guardian-Berechtigung ist für dieses Kind erforderlich.")


def _custody_authority(membership):
    return SimpleNamespace(
        membership=membership,
        membership_id=membership.id,
        can_manage_account=True,
        source="custody",
    )


def require_child_guardian(user, baby, *, manage=False):
    membership = active_membership(user, baby.family)

    # #717: Sorgerecht ist die kanonische fachliche Quelle. Der Zugriff wird
    # dynamisch abgeleitet; eine zusätzliche ManagedChildGuardian-Zeile ist
    # weder für bestehende noch für neue Sorgerechtsangaben erforderlich.
    if _custody_guardian_allowed(membership, baby):
        return membership, _custody_authority(membership)

    # Bestehende explizite Guardian-Zeilen bleiben während der Migration als
    # technische Legacy-Kompatibilität gültig, behaupten aber kein Sorgerecht.
    guardian = ManagedChildGuardian.objects.filter(
        baby=baby,
        membership=membership,
    ).first()
    if guardian and (not manage or guardian.can_manage_account):
        return membership, guardian

    # Legacy #147 rows can predate per-child guardian rows. Bootstrap only from
    # an explicitly marked Care Circle guardian, never from Owner/Adult role alone.
    if not baby.guardians.exists() and _bootstrap_guardian_allowed(membership, baby):
        guardian = ManagedChildGuardian.objects.create(
            baby=baby,
            membership=membership,
            can_manage_account=True,
        )
        return membership, guardian
    raise PermissionDenied("Sorgerecht oder eine bestehende Guardian-Berechtigung ist für dieses Kind erforderlich.")


def child_scope_access(user, baby, scope):
    """Authorize child-scoped health/care access consistently.

    Custody and legacy Guardian authority grant the full former Guardian scope.
    Existing Care Circle grants remain an independent compatibility path.
    """
    require_module(baby.family)
    try:
        membership, authority = require_child_guardian(user, baby)
    except PermissionDenied:
        return care_access(user, baby.family, scope, baby=baby)
    return membership, SimpleNamespace(
        can_view_pregnancy=False,
        can_log_care=True,
        can_view_growth_development=True,
        is_guardian=True,
        source=getattr(authority, "source", "legacy_guardian"),
    )


def child_access_overview(user, family):
    """Bulk projection of the same custody/legacy/care policy, without granting rights."""
    actor = active_membership(user, family)
    global_access = CareCircleAccess.objects.filter(family=family, membership=actor, baby__isnull=True).first()
    custody_ids = set(FamilyRelationship.objects.filter(
        family=family, related_membership=actor, has_custody=True,
        status=FamilyRelationship.Status.ACTIVE, child_membership__role=Membership.Role.CHILD,
    ).values_list("child_membership_id", flat=True)) if actor.role in MANAGER_ROLES else set()
    grants = {row.baby_id: row for row in CareCircleAccess.objects.filter(family=family, membership=actor, baby__isnull=False)}
    result = []
    for baby in BabyProfile.objects.filter(family=family, active=True).select_related("membership", "family").prefetch_related("guardians"):
        guardians = list(baby.guardians.all())
        legacy = next((row for row in guardians if row.membership_id == actor.id), None)
        bootstrap = not guardians and bool(global_access and global_access.is_guardian)
        authority = baby.membership_id in custody_ids or bool(legacy) or bootstrap
        grant = grants.get(baby.id)
        care = authority or bool(global_access and global_access.can_log_care) or bool(grant and grant.can_log_care)
        growth = authority or bool(global_access and global_access.can_view_growth_development) or bool(grant and grant.can_view_growth_development)
        if not care and not growth:
            continue
        manage = baby.membership_id in custody_ids or bool(legacy and legacy.can_manage_account) or bootstrap
        result.append((baby, {
            "can_log_care": care, "can_view_growth_development": growth,
            "can_manage_account": manage, "can_manage_care_circle": manage,
            "is_guardian": authority,
            "source": "custody" if baby.membership_id in custody_ids else "legacy_guardian" if authority else "care_circle",
        }))
    return global_access, result


@transaction.atomic
def attach_existing_child(user, child, *, birth_date, client_identity_key):
    require_child_membership_guardian(user, child, manage=True)
    child = Membership.objects.select_for_update().select_related("family", "user").get(pk=child.pk)
    existing = BabyProfile.objects.filter(membership=child).first()
    if existing:
        return existing
    if BabyProfile.objects.filter(client_identity_key=client_identity_key).exists():
        raise ValidationError({"client_identity_key": "This creation key is already in use."})
    profile, _ = UserProfile.objects.get_or_create(user=child.user)
    known = (profile.birth_year, profile.birth_month, profile.birth_day)
    if all(known) and known != (birth_date.year, birth_date.month, birth_date.day):
        raise ValidationError({"birth_date": "Use the birthday of the existing child profile."})
    if not all(known):
        profile.birth_year, profile.birth_month, profile.birth_day = birth_date.year, birth_date.month, birth_date.day
        profile.save(update_fields=["birth_year", "birth_month", "birth_day", "updated_at"])
    return BabyProfile.objects.create(family=child.family,membership=child,display_name=child.display_name or child.user.get_username(),
        birth_date=birth_date,client_identity_key=client_identity_key,created_by=user)


def _require_guardian_manager_or_owner_bootstrap(user, baby):
    """Authorize legacy Guardian-list writes without creating new Owner power.

    #717 supersedes the former Owner bootstrap: custody is now the canonical
    authority. Existing account-managing Guardian rows remain writable only as
    migration compatibility.
    """
    membership = active_membership(user, baby.family)
    if _custody_guardian_allowed(membership, baby):
        return membership, _custody_authority(membership), False

    guardian = ManagedChildGuardian.objects.filter(
        baby=baby,
        membership=membership,
        can_manage_account=True,
    ).first()
    if guardian:
        return membership, guardian, False

    if not baby.guardians.exists() and _bootstrap_guardian_allowed(membership, baby):
        guardian = ManagedChildGuardian.objects.create(
            baby=baby,
            membership=membership,
            can_manage_account=True,
        )
        return membership, guardian, False

    raise PermissionDenied("Sorgerecht oder eine bestehende kontoverwaltende Guardian-Berechtigung ist erforderlich.")


def _custody_rows(baby):
    if not baby.membership_id:
        return []
    return list(
        FamilyRelationship.objects.filter(
            family=baby.family,
            child_membership_id=baby.membership_id,
            has_custody=True,
            status=FamilyRelationship.Status.ACTIVE,
            related_membership__role__in=MANAGER_ROLES,
        )
        .select_related("related_membership__user")
        .order_by("created_at")
    )


def _serialize_guardian_rows(baby):
    effective = {}
    for relation in _custody_rows(baby):
        membership = relation.related_membership
        effective[str(membership.id)] = {
            "membership": str(membership.id),
            "display_name": membership.display_name or membership.user.get_username(),
            "can_manage_account": True,
            "source": "custody",
            "has_custody": True,
        }
    for row in baby.guardians.select_related("membership__user").order_by("created_at"):
        key = str(row.membership_id)
        effective.setdefault(
            key,
            {
                "membership": key,
                "display_name": row.membership.display_name or row.membership.user.get_username(),
                "can_manage_account": row.can_manage_account,
                "source": "legacy_guardian",
                "has_custody": False,
            },
        )
    return list(effective.values())


def serialize_child_identity(baby):
    user = baby.membership.user if baby.membership_id else None
    primary = primary_identity(user) if user else None
    pending = pending_identity(user) if user else None
    active = bool(user and user.has_usable_password() and primary and primary.verified_at)
    if active:
        state = "active"
    elif pending:
        state = "verification_pending"
    else:
        state = "managed"
    email = primary.email if primary else pending.email if pending else ""
    return {
        "baby": str(baby.pk),
        "membership": str(baby.membership_id) if baby.membership_id else None,
        "user": user.pk if user else None,
        "display_name": baby.display_name,
        "role": baby.membership.role if baby.membership_id else None,
        "access_state": state,
        "email_hint": _masked_email(email),
        "guardians": _serialize_guardian_rows(baby),
    }


def guardian_settings_for_family(user, family):
    """Return permission metadata only; never child health/profile payloads."""
    actor = active_membership(user, family)
    legacy_guardian = CareCircleAccess.objects.filter(
        family=family,
        membership=actor,
        baby__isnull=True,
        is_guardian=True,
    ).exists()
    babies = (
        BabyProfile.objects.filter(
            family=family,
            membership__isnull=False,
            membership__role=Membership.Role.CHILD,
        )
        .select_related("membership__user")
        .prefetch_related("guardians__membership__user")
        .order_by("display_name", "created_at")
    )
    result = []
    for baby in babies:
        guardians = list(baby.guardians.all())
        custody = _custody_rows(baby)
        custody_ids = {row.related_membership_id for row in custody}
        has_account_manager = bool(custody_ids) or any(row.can_manage_account for row in guardians)
        actor_manages = actor.id in custody_ids or any(
            row.membership_id == actor.id and row.can_manage_account
            for row in guardians
        )
        legacy_can_manage = not guardians and not custody_ids and legacy_guardian
        can_manage = actor_manages or legacy_can_manage
        if actor.role != Membership.Role.OWNER and not can_manage:
            continue
        result.append(
            {
                "baby": str(baby.pk),
                "membership": str(baby.membership_id),
                "display_name": baby.display_name,
                "guardians": _serialize_guardian_rows(baby),
                "custody_memberships": [
                    {
                        "membership": str(row.related_membership_id),
                        "display_name": row.related_membership.display_name
                        or row.related_membership.user.get_username(),
                    }
                    for row in custody
                ],
                "has_account_managing_guardian": has_account_manager,
                "can_manage_guardians": can_manage,
                "can_bootstrap_guardians": False,
                "custody_is_authority": True,
            }
        )
    return {
        "family": str(family.pk),
        "family_name": family.name,
        "actor_membership": str(actor.pk),
        "actor_role": actor.role,
        "children": result,
    }


def _masked_email(value):
    value = str(value or "")
    if "@" not in value:
        return ""
    local, domain = value.rsplit("@", 1)
    return f"{local[:1]}•••@{domain}" if local else f"•••@{domain}"


@transaction.atomic
def replace_child_guardians(user, baby_id, rows):
    baby = child_profile(baby_id, for_update=True)
    if not baby.membership_id:
        raise ValidationError("Child identity must be reconciled before guardians can be managed.")
    _require_guardian_manager_or_owner_bootstrap(user, baby)
    if not isinstance(rows, list) or not rows:
        raise ValidationError({"guardians": "At least one account-managing authority is required."})

    family_memberships = {
        str(row.pk): row
        for row in Membership.objects.filter(family=baby.family, family__status="active").select_related("user")
    }
    existing_legacy_ids = set(
        ManagedChildGuardian.objects.filter(baby=baby).values_list("membership_id", flat=True)
    )
    normalized = {}
    for item in rows:
        membership_id = str(item.get("membership") or "")
        membership = family_memberships.get(membership_id)
        if not membership:
            raise ValidationError({"membership": "Guardian membership does not belong to this family."})
        if membership.role not in MANAGER_ROLES:
            raise ValidationError({"membership": "Only owner/adult memberships can hold child authority."})
        if membership.id not in existing_legacy_ids and not _custody_guardian_allowed(membership, baby):
            raise ValidationError(
                {"membership": "Neue Kinderberechtigungen werden über Sorgerecht vergeben; eine separate Guardian-Freigabe ist nicht mehr möglich."}
            )
        normalized[membership_id] = bool(item.get("can_manage_account", True))
    if not any(normalized.values()):
        raise ValidationError({"guardians": "At least one authority must be able to manage the child account."})

    ManagedChildGuardian.objects.filter(baby=baby).exclude(membership_id__in=normalized).delete()
    for membership_id, can_manage in normalized.items():
        ManagedChildGuardian.objects.update_or_create(
            baby=baby,
            membership=family_memberships[membership_id],
            defaults={"can_manage_account": can_manage},
        )
    return child_profile(baby.pk)


@transaction.atomic
def begin_child_login_activation(user, baby_id, *, email, password):
    baby = child_profile(baby_id, for_update=True)
    require_child_guardian(user, baby, manage=True)
    if not baby.membership_id or baby.membership.role != Membership.Role.CHILD:
        raise ValidationError("Managed child membership is required.")

    child_user = User.objects.select_for_update().get(pk=baby.membership.user_id)
    current = primary_identity(child_user)
    if current and current.verified_at and child_user.has_usable_password():
        raise ValidationError({"detail": "Child login is already active."})

    try:
        validate_password(password, user=child_user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": list(exc.messages)}) from exc

    try:
        identity = request_pending_email(child_user, email)
    except (EmailConflictError, EmailIdentityError) as exc:
        raise ValidationError({"email": str(exc)}) from exc

    child_user.set_password(password)
    child_user.save(update_fields=["password"])
    identity = queue_verification(identity, locale=baby.family.locale)
    return baby, identity


def child_login_is_active(baby):
    if not baby.membership_id:
        return False
    user = baby.membership.user
    identity = primary_identity(user)
    return bool(user.has_usable_password() and identity and identity.verified_at)


def _technical_username_for_existing_baby(baby):
    return f"child-{baby.family_id.hex[:8]}-{baby.id.hex[:20]}"


def _identity_key(baby):
    return baby.family_id, baby.display_name.strip().casefold(), baby.birth_date


@transaction.atomic
def attach_identity_to_orphan_baby(baby_id):
    baby = child_profile(baby_id, for_update=True)
    if baby.membership_id:
        return baby, False

    username = _technical_username_for_existing_baby(baby)
    if User.objects.filter(username=username).exists():
        raise ValidationError("Deterministic child username is already occupied; manual review required.")

    child_user = User(username=username, email="", is_active=True)
    child_user.set_unusable_password()
    child_user.save()
    membership = Membership.objects.create(
        family=baby.family,
        user=child_user,
        role=Membership.Role.CHILD,
        display_name=baby.display_name,
        birthday_visibility=Membership.BirthdayVisibility.FULL_DATE,
    )
    UserProfile.objects.create(
        user=child_user,
        birth_year=baby.birth_date.year,
        birth_month=baby.birth_date.month,
        birth_day=baby.birth_date.day,
    )
    baby.membership = membership
    baby.save(update_fields=["membership", "updated_at"])

    for access in CareCircleAccess.objects.filter(
        family=baby.family,
        baby__isnull=True,
        is_guardian=True,
        membership__role__in=MANAGER_ROLES,
    ).select_related("membership"):
        ManagedChildGuardian.objects.get_or_create(
            baby=baby,
            membership=access.membership,
            defaults={"can_manage_account": True},
        )
    return baby, True


def reconcile_orphan_child_identities(*, apply=False):
    rows = list(
        BabyProfile.objects.filter(membership__isnull=True)
        .select_related("family")
        .order_by("family_id", "birth_date", "display_name", "created_at")
    )
    keys = [_identity_key(row) for row in rows]
    counts = Counter(keys)
    linked_keys = {
        _identity_key(row)
        for row in BabyProfile.objects.filter(membership__isnull=False).only(
            "family_id", "display_name", "birth_date"
        )
    }
    guardian_family_ids = set(
        CareCircleAccess.objects.filter(
            baby__isnull=True,
            is_guardian=True,
            membership__role__in=MANAGER_ROLES,
        ).values_list("family_id", flat=True)
    )
    explicit_guardian_babies = set(
        ManagedChildGuardian.objects.filter(
            can_manage_account=True,
            membership__role__in=MANAGER_ROLES,
            baby__membership__isnull=True,
        ).values_list("baby_id", flat=True)
    )

    result = {"reconciled": [], "review": []}
    for baby, key in zip(rows, keys):
        ambiguous_identity = counts[key] > 1 or key in linked_keys
        has_guardian_seed = baby.family_id in guardian_family_ids or baby.pk in explicit_guardian_babies
        if ambiguous_identity or not has_guardian_seed:
            result["review"].append(str(baby.pk))
            continue
        if apply:
            attached, _ = attach_identity_to_orphan_baby(baby.pk)
            result["reconciled"].append(str(attached.pk))
        else:
            result["reconciled"].append(str(baby.pk))
    return result
