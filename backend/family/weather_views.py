from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Family
from .weather_service import weather_payload


@api_view(["GET"])
def weather(request):
    family_id=request.query_params.get("family")
    families=Family.objects.filter(memberships__user=request.user).distinct()
    family=families.filter(id=family_id).first() if family_id else families.first()
    if family_id and not family:
        raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
    if not family:
        return Response({"source":{"provider":"Open-Meteo","status":"missing","stale":False,"last_success_at":None,"location":{}},"current":None,"days":[],"alerts":[]})
    return Response(weather_payload(family))
