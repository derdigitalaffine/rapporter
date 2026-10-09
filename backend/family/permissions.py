from rest_framework.permissions import BasePermission

from .models import Family, Membership


class ActiveTenantAccess(BasePermission):
    """Require a usable tenant for normal accounts while leaving superadmins global.

    Object/queryset isolation remains enforced by the family-scoped viewsets. This
    permission additionally makes a suspended single-tenant account unusable and
    validates explicit family parameters before a view can mutate tenant data.
    """

    message = "Diese Familie ist derzeit nicht aktiv."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        family_id = request.query_params.get("family")
        if not family_id and request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                family_id = request.data.get("family")
            except Exception:
                family_id = None
        if family_id:
            return Membership.objects.filter(
                user=user,
                family_id=family_id,
                family__status=Family.Status.ACTIVE,
            ).exists()

        # Public invitation endpoints override DEFAULT_PERMISSION_CLASSES with
        # AllowAny. For all authenticated app endpoints, at least one active tenant
        # is required. A user can still be a member of another suspended tenant;
        # queryset scoping prevents cross-tenant object access.
        return Membership.objects.filter(user=user, family__status=Family.Status.ACTIVE).exists()
