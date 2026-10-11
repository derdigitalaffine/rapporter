from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from family.superadmin_views import IsSuperAdmin

from .service import mail_health_summary
from .smtp_config import public_config


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_mail_health(request):
    """Expose only the redacted operational mail summary to superadmins."""
    summary = mail_health_summary()
    effective = public_config()
    summary["configured"] = effective["configured"]
    summary["configuration_source"] = effective["effective_source"]
    return Response(summary)
