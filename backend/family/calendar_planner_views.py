from uuid import UUID

from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .calendar_planner_models import CalendarPlannerPreference
from .models import Family, Membership


SPECIAL_LANE_IDS = {"__family__", "__ics__"}
MAX_LANES = 200
MAX_LANE_ID_LENGTH = 80


def _membership(request, family_id):
    return (
        Membership.objects.filter(
            user=request.user,
            family_id=family_id,
            family__status=Family.Status.ACTIVE,
        )
        .select_related("family")
        .first()
    )


def _validated_lane_order(value, family_id):
    if not isinstance(value, list):
        raise ValueError("Lane-Reihenfolge muss eine Liste sein.")
    if len(value) > MAX_LANES:
        raise ValueError("Lane-Reihenfolge enthält zu viele Einträge.")
    allowed = SPECIAL_LANE_IDS | {
        str(item)
        for item in Membership.objects.filter(family_id=family_id).values_list("id", flat=True)
    }
    result = []
    for raw in value:
        if not isinstance(raw, str):
            raise ValueError("Lane-IDs müssen Textwerte sein.")
        lane_id = raw.strip()
        if not lane_id or len(lane_id) > MAX_LANE_ID_LENGTH:
            raise ValueError("Ungültige Lane-ID.")
        if lane_id not in allowed or lane_id in result:
            continue
        result.append(lane_id)
    return result


@api_view(["GET", "PATCH"])
@permission_classes([permissions.IsAuthenticated])
def calendar_planner_preferences(request):
    raw_family_id = request.query_params.get("family") or request.data.get("family")
    if not raw_family_id:
        return Response({"detail": "Familie fehlt."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        family_id = UUID(str(raw_family_id))
    except (TypeError, ValueError, AttributeError):
        return Response({"detail": "Ungültige Familie."}, status=status.HTTP_400_BAD_REQUEST)
    membership = _membership(request, family_id)
    if not membership:
        return Response({"detail": "Familie ist für diesen Benutzer nicht verfügbar."}, status=status.HTTP_403_FORBIDDEN)
    preference = CalendarPlannerPreference.objects.filter(
        user=request.user,
        family_id=membership.family_id,
    ).first()
    if request.method == "PATCH":
        try:
            lane_order = _validated_lane_order(request.data.get("lane_order", []), membership.family_id)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        preference, _ = CalendarPlannerPreference.objects.update_or_create(
            user=request.user,
            family_id=membership.family_id,
            defaults={"lane_order": lane_order},
        )
    return Response(
        {
            "family": str(membership.family_id),
            "lane_order": list(preference.lane_order or []) if preference else [],
        }
    )