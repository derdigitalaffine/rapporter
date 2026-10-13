"""Finance uses the canonical tenant and entitlement policy at every API boundary."""
from entitlements.services import require_capability, resolve_entitlements_for_families
from family.models import Family
from family.permissions import ActiveTenantAccess


class ExpenseAccess(ActiveTenantAccess):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        family_id = request.query_params.get("family")
        if not family_id and request.method not in {"GET", "HEAD", "OPTIONS"}:
            family_id = request.data.get("family")
        if family_id:
            family = Family.objects.filter(id=family_id, memberships__user=request.user).first()
            if not family:
                return False
            require_capability(request.user, family, "expenses")
        return True

    def has_object_permission(self, request, view, obj):
        require_capability(request.user, obj.family, "expenses")
        return True


def finance_queryset(queryset, user):
    families = Family.objects.filter(memberships__user=user, status=Family.Status.ACTIVE).distinct()
    snapshots = resolve_entitlements_for_families(families)
    allowed = [key for key, value in snapshots.items() if "expenses" in value.capabilities]
    return queryset.filter(family_id__in=allowed)
