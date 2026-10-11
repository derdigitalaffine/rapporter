from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .matomo import MatomoError, get_matomo_config, public_matomo_config, reporting_snapshot
from .superadmin_views import IsSuperAdmin


_ALLOWED_WINDOWS = {7, 30, 90}


def _date_range(days):
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    return f"{start.isoformat()},{end.isoformat()}"


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_matomo_status(request):
    config = get_matomo_config()
    payload = public_matomo_config()
    payload["window_options"] = sorted(_ALLOWED_WINDOWS)
    payload["auth_token_configured"] = bool(config.auth_token)
    return Response(payload)


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def superadmin_matomo_report(request):
    try:
        days = int(request.query_params.get("days", "30"))
    except (TypeError, ValueError):
        days = 30
    if days not in _ALLOWED_WINDOWS:
        return Response(
            {"detail": "Ungültiges Analysefenster.", "allowed_days": sorted(_ALLOWED_WINDOWS)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    config = get_matomo_config()
    if not config.configured:
        return Response(
            {
                "detail": "Matomo ist nicht vollständig konfiguriert.",
                "configured": False,
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    date_range = _date_range(days)
    try:
        snapshot = reporting_snapshot(date_range=date_range)
    except MatomoError as exc:
        return Response(
            {
                "detail": str(exc),
                "configured": True,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        {
            "configured": True,
            "site_id": config.site_id,
            "days": days,
            "date_range": date_range,
            **snapshot,
        }
    )
