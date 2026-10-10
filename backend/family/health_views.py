from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from mailing.service import mail_health_summary


class IsSuperAdminHealth(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def health(request):
    return Response({"status": "ok", "service": "FamilyOS"})


@api_view(["GET"])
@permission_classes([IsSuperAdminHealth])
def superadmin_mail_health(request):
    return Response(mail_health_summary())
