from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Family
from .predictions import (
    accept_all_shopping_predictions,
    accept_shopping_prediction,
    shopping_predictions,
    suppress_shopping_prediction,
)
from .serializers import ShoppingItemSerializer


def _family(request):
    family_id = request.query_params.get("family") or request.data.get("family")
    family = Family.objects.filter(id=family_id, memberships__user=request.user).distinct().first()
    if not family:
        raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
    return family


@api_view(["GET"])
def shopping_prediction_list(request):
    family = _family(request)
    list_id = request.query_params.get("list") or None
    try:
        result = shopping_predictions(family, list_id=list_id)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(result)


@api_view(["POST"])
def shopping_prediction_accept(request):
    family = _family(request)
    key = request.data.get("key")
    try:
        item, created = accept_shopping_prediction(
            family,
            key,
            request.user,
            list_id=request.data.get("list") or None,
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"item": ShoppingItemSerializer(item, context={"request": request}).data, "created": created},
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(["POST"])
def shopping_prediction_accept_all(request):
    family = _family(request)
    try:
        items = accept_all_shopping_predictions(
            family,
            request.user,
            list_id=request.data.get("list") or None,
        )
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({
        "created": len(items),
        "items": ShoppingItemSerializer(items, many=True, context={"request": request}).data,
    })


@api_view(["POST"])
def shopping_prediction_feedback(request):
    family = _family(request)
    action = str(request.data.get("action") or "snoozed")
    if action not in {"snoozed", "dismissed"}:
        return Response({"detail": "Unbekannte Feedback-Aktion."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        row = suppress_shopping_prediction(
            family,
            request.data.get("key"),
            action=action,
            days=request.data.get("days") or 7,
        )
    except (TypeError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({
        "key": row.normalized_name,
        "action": row.action,
        "suppress_until": row.suppress_until,
        "dismiss_count": row.dismiss_count,
    })
