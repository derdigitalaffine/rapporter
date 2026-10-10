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


def care_access(user, family, scope="pregnancy"):
    require_module(family)
    membership = active_membership(user, family)
    access = CareCircleAccess.objects.filter(family=family, membership=membership).first()
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
            defaults={
                "can_view_pregnancy": True,
                "can_log_care": True,
                "can_view_growth_development": True,
                "is_guardian": True,
            },
        )
    else:
        setting.disabled_at = now
    setting.save()
    return setting


def set_care_circle(user, family, rows):
    require_manager(user, family)
    require_module(family)
    if not isinstance(rows, list):
        raise ValidationError("care_circle must be a list.")
    memberships = {str(m.id): m for m in Membership.objects.filter(family=family, family__status="active")}
    seen = set()
    result = []
    for row in rows:
        membership_id = str(row.get("membership") or "")
        membership = memberships.get(membership_id)
        if not membership:
            raise ValidationError({"membership": "Membership does not belong to this family."})
        guardian = bool(row.get("is_guardian", False))
        if guardian and membership.role not in MANAGER_ROLES:
            raise ValidationError({"is_guardian": "Only owner/adult memberships can manage a child account."})
        seen.add(membership_id)
        access, _ = CareCircleAccess.objects.update_or_create(
            family=family,
            membership=membership,
            defaults={
                "can_view_pregnancy": bool(row.get("can_view_pregnancy", False)),
                "can_log_care": bool(row.get("can_log_care", False)),
                "can_view_growth_development": bool(row.get("can_view_growth_development", False)),
                "is_guardian": guardian,
            },
        )
        result.append(access)
    CareCircleAccess.objects.filter(family=family).exclude(membership_id__in=seen).delete()
    return result
