from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from baby.models import FamilyModuleSetting
from family.models import Membership

from .models import PetCareAccess

MODULE_KEY = "pet_care"
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
        raise NotFound("Pet Care is not enabled for this family.")
    return family


def require_manager(user, family):
    membership = active_membership(user, family)
    if membership.role not in MANAGER_ROLES:
        raise PermissionDenied("Only family owners and adults can manage Pet Care.")
    return membership


def pet_access(user, family, *, health=False):
    require_module(family)
    membership = active_membership(user, family)
    access = PetCareAccess.objects.filter(family=family, membership=membership).first()
    if not access or not access.can_care:
        raise PermissionDenied("This member is not in the Pet Care circle.")
    if health and not access.health_manage:
        raise PermissionDenied("This member cannot manage pet health data.")
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
    if enabled:
        setting.enabled_by = user
        setting.enabled_at = setting.enabled_at or now
        setting.disabled_at = None
        PetCareAccess.objects.get_or_create(
            family=family,
            membership=membership,
            defaults={"can_care": True, "health_manage": True, "remind_medications": True, "remind_prevention": True},
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
    memberships = {str(row.id): row for row in Membership.objects.filter(family=family, family__status="active")}
    seen = set()
    result = []
    for item in rows:
        membership_id = str(item.get("membership") or "")
        membership = memberships.get(membership_id)
        if not membership:
            raise ValidationError({"membership": "Membership does not belong to this family."})
        health_manage = bool(item.get("health_manage", False))
        if health_manage and membership.role not in MANAGER_ROLES:
            raise ValidationError({"health_manage": "Only owner/adult memberships can manage pet health plans."})
        seen.add(membership_id)
        access, _ = PetCareAccess.objects.update_or_create(
            family=family,
            membership=membership,
            defaults={"can_care": bool(item.get("can_care", True)), "health_manage": health_manage, "remind_medications": bool(item.get("remind_medications", True)), "remind_prevention": bool(item.get("remind_prevention", True))},
        )
        result.append(access)
    PetCareAccess.objects.filter(family=family).exclude(membership_id__in=seen).delete()
    return result
