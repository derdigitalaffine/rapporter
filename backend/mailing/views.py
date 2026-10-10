from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from family.superadmin_views import IsSuperAdmin

from .service import mail_health_summary


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_mail_health(request):
    """Expose only the redacted operational mail summary to superadmins."""
    return Response(mail_health_summary())
