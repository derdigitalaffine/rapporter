from __future__ import annotations

from collections import Counter

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
from family.models import Membership, UserProfile

from .family_modules import MANAGER_ROLES, active_membership
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
        is_guardian=True,
    ).exists()


def require_child_guardian(user, baby, *, manage=False):
    membership = active_membership(user, baby.family)
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
    raise PermissionDenied("Explicit guardian permission is required for this child.")


def _require_guardian_manager_or_owner_bootstrap(user, baby):
    """Authorize Guardian-list writes without turning Owner into a Guardian.

    Existing account-managing Guardians remain authoritative. The only Owner
    exception is recovery from a child that currently has no account-managing
    Guardian at all. That exception is deliberately scoped to this write path;
    protected child reads continue to use ``require_child_guardian``.
    """
    membership = active_membership(user, baby.family)
    guardian = ManagedChildGuardian.objects.filter(
        baby=baby,
        membership=membership,
        can_manage_account=True,
    ).first()
    if guardian:
        return membership, guardian, False

    # Preserve the legacy #147 Care Circle migration bridge for an explicitly
    # marked guardian. This still never derives permission from Owner/Adult.
    if not baby.guardians.exists() and _bootstrap_guardian_allowed(membership, baby):
        guardian = ManagedChildGuardian.objects.create(
            baby=baby,
            membership=membership,
            can_manage_account=True,
        )
        return membership, guardian, False

    has_account_manager = ManagedChildGuardian.objects.filter(
        baby=baby,
        can_manage_account=True,
    ).exists()
    if membership.role == Membership.Role.OWNER and not has_account_manager:
        return membership, None, True
    raise PermissionDenied("An account-managing guardian is required to change guardians for this child.")


def _serialize_guardian_rows(baby):
    return [
        {
            "membership": str(row.membership_id),
            "display_name": row.membership.display_name or row.membership.user.get_username(),
            "can_manage_account": row.can_manage_account,
        }
        for row in baby.guardians.select_related("membership__user").order_by("created_at")
    ]


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
        has_account_manager = any(row.can_manage_account for row in guardians)
        actor_manages = any(
            row.membership_id == actor.id and row.can_manage_account
            for row in guardians
        )
        legacy_can_manage = not guardians and legacy_guardian
        owner_bootstrap = actor.role == Membership.Role.OWNER and not has_account_manager
        can_manage = actor_manages or legacy_can_manage or owner_bootstrap
        if actor.role != Membership.Role.OWNER and not can_manage:
            continue
        result.append(
            {
                "baby": str(baby.pk),
                "membership": str(baby.membership_id),
                "display_name": baby.display_name,
                "guardians": [
                    {
                        "membership": str(row.membership_id),
                        "display_name": row.membership.display_name or row.membership.user.get_username(),
                        "can_manage_account": row.can_manage_account,
                    }
                    for row in guardians
                ],
                "has_account_managing_guardian": has_account_manager,
                "can_manage_guardians": can_manage,
                "can_bootstrap_guardians": owner_bootstrap and not actor_manages,
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
        raise ValidationError({"guardians": "At least one account-managing guardian is required."})

    family_memberships = {
        str(row.pk): row
        for row in Membership.objects.filter(family=baby.family, family__status="active").select_related("user")
    }
    normalized = {}
    for item in rows:
        membership_id = str(item.get("membership") or "")
        membership = family_memberships.get(membership_id)
        if not membership:
            raise ValidationError({"membership": "Guardian membership does not belong to this family."})
        if membership.role not in MANAGER_ROLES:
            raise ValidationError({"membership": "Only owner/adult memberships can be guardians."})
        normalized[membership_id] = bool(item.get("can_manage_account", True))
    if not any(normalized.values()):
        raise ValidationError({"guardians": "At least one guardian must be able to manage the child account."})

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

    # The password alone cannot authenticate until the pending address becomes a
    # verified PRIMARY EmailIdentity, so no login is enabled before mailbox proof.
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

    # Legacy Care Circle guardian flags are used only to seed explicit per-child
    # rows. Owner/Adult role alone never grants guardian authority.
    for access in CareCircleAccess.objects.filter(
        family=baby.family,
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