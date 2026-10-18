from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from family.models import Membership

from .models import CareCircleAccess, FamilyModuleSetting


MODULE_KEY = "pregnancy_baby"
MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.ADULT}


def active_membership(user, family):
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")
    membership = Membership.objects.filter(family=family, user=user, family__status="active").first()
    if not membership:
        raise PermissionDenied("Active family membership required.")
    return membership


def module_setting(family):
    setting, _ = FamilyModuleSetting.objects.get_or_create(family=family, module_key=MODULE_KEY)
    return setting


def module_enabled(family):
    return FamilyModuleSetting.objects.filter(family=family, module_key=MODULE_KEY, enabled=True).exists()


def require_module(family):
    if not module_enabled(family):
        raise NotFound("Pregnancy & Baby is not enabled for this family.")
    return family


def require_manager(user, family):
    membership = active_membership(user, family)
    if membership.role not in MANAGER_ROLES:
        raise PermissionDenied("Only family owners and adults can manage this module.")
    return membership


def care_access(user, family, scope="pregnancy", *, baby=None):
    require_module(family)
    membership = active_membership(user, family)
    access = CareCircleAccess.objects.filter(family=family, membership=membership, baby__isnull=True).first()
    if baby is not None and scope != "pregnancy":
        scoped = CareCircleAccess.objects.filter(family=family, membership=membership, baby=baby).first()
        if scoped:
            from types import SimpleNamespace
            access = SimpleNamespace(
                can_view_pregnancy=False,
                can_log_care=scoped.can_log_care or bool(access and access.can_log_care),
                can_view_growth_development=scoped.can_view_growth_development or bool(access and access.can_view_growth_development),
                is_guardian=False,
            )
    if not access:
        raise PermissionDenied("This member is not in the Pregnancy & Baby Care Circle.")
    allowed = {
        "pregnancy": access.can_view_pregnancy,
        "care": access.can_log_care,
        "growth": access.can_view_growth_development,
        "development": access.can_view_growth_development,
        "report": access.can_view_growth_development or access.can_log_care,
    }.get(scope)
    if not allowed:
        raise PermissionDenied("The Care Circle permission does not cover this area.")
    return membership, access


def set_module(user, family, *, enabled, show_in_main_navigation=None):
    membership = require_manager(user, family)
    setting = module_setting(family)
    now = timezone.now()
    setting.enabled = bool(enabled)
    if show_in_main_navigation is not None:
        setting.show_in_main_navigation = bool(show_in_main_navigation) if enabled else False
    elif not enabled:
        setting.show_in_main_navigation = False
    setting.enabled_by = user if enabled else setting.enabled_by
    if enabled:
        setting.enabled_at = setting.enabled_at or now
        setting.disabled_at = None
        CareCircleAccess.objects.get_or_create(
            family=family,
            membership=membership,
            baby=None,
            defaults={
                "can_view_pregnancy": True,
                "can_log_care": False,
                "can_view_growth_development": False,
                "is_guardian": False,
            },
        )
    else:
        setting.disabled_at = now
    setting.save()
    return setting


@transaction.atomic
def set_care_circle(user, family, rows, *, baby=None):
    from .child_identity_service import require_child_guardian
    if baby:
        require_child_guardian(user, baby, manage=True)
    else:
        require_manager(user, family)
    require_module(family)
    if not isinstance(rows, list):
        raise ValidationError("care_circle must be a list.")
    if baby is None:
        old = {str(row.membership_id): row for row in CareCircleAccess.objects.filter(family=family, baby__isnull=True)}
        next_rows = {str(row.get("membership")): row for row in rows if isinstance(row, dict)}
        health_changed = any(
            bool(getattr(old.get(key), flag, False)) != bool(next_rows.get(key, {}).get(flag, False))
            for key in old.keys() | next_rows.keys()
            for flag in ("can_log_care", "can_view_growth_development", "is_guardian")
        )
        if health_changed:
            for child in family.baby_profiles.filter(active=True):
                require_child_guardian(user, child, manage=True)
    memberships = {str(m.id): m for m in Membership.objects.filter(family=family, family__status="active")}
    seen = set()
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError({"care_circle": "Use objects for care permissions."})
        membership_id = str(row.get("membership") or "")
        membership = memberships.get(membership_id)
        if not membership:
            raise ValidationError({"membership": "Membership does not belong to this family."})
        if membership_id in seen:
            raise ValidationError({"membership": "Choose each membership once."})
        guardian = bool(row.get("is_guardian", False))
        existing = CareCircleAccess.objects.filter(family=family, membership=membership, baby=baby).first()
        if guardian and (baby or not existing or not existing.is_guardian):
            raise ValidationError({"is_guardian": "Use confirmed custody, not a separate Guardian grant."})
        if baby and row.get("can_view_pregnancy"):
            raise ValidationError({"can_view_pregnancy": "Child care grants do not include pregnancy data."})
        seen.add(membership_id)
        access, _ = CareCircleAccess.objects.update_or_create(
            family=family,
            membership=membership,
            baby=baby,
            defaults={
                "can_view_pregnancy": bool(row.get("can_view_pregnancy", False)),
                "can_log_care": bool(row.get("can_log_care", False)),
                "can_view_growth_development": bool(row.get("can_view_growth_development", False)),
                "is_guardian": bool(existing and existing.is_guardian) if not baby else False,
            },
        )
        result.append(access)
    CareCircleAccess.objects.filter(family=family, baby=baby).exclude(membership_id__in=seen).delete()
    return result
