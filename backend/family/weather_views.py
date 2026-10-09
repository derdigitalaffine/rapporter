from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Family
from .weather_contract import build_weather_contract


def _weather_family(request):
    families = Family.objects.filter(
        memberships__user=request.user,
        status=Family.Status.ACTIVE,
    ).distinct()
    family_id = request.query_params.get("family")
    if family_id:
        family = families.filter(id=family_id).first()
        if not family:
            raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
        return family
    return families.first()


@api_view(["GET"])
def weather(request):
    family = _weather_family(request)
    if not family:
        return Response({
            "source": {
                "id": None,
                "provider": "",
                "last_success_at": None,
                "last_attempt_at": None,
                "last_sync_status": "missing",
                "last_sync_error": "",
                "stale": False,
                "location": {"latitude": None, "longitude": None, "label": ""},
            },
            "current": None,
            "days": [],
            "alerts": [],
        })
    return Response(build_weather_contract(family))
