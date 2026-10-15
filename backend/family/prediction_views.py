from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Family, ShoppingList
from .predictions import (
    accept_all_shopping_predictions,
    accept_shopping_prediction,
    shopping_predictions,
    suppress_shopping_prediction,
)
from .serializers import ShoppingItemSerializer
from .shopping_access import can_access_shopping_list, set_shopping_access, visible_shopping_lists


def _family(request):
    family_id = request.query_params.get("family") or request.data.get("family")
    family = Family.objects.filter(id=family_id, memberships__user=request.user).distinct().first()
    if not family:
        raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
    return family


def _visible_list_id(request, family, raw_id, *, use_default=False):
    rows = visible_shopping_lists(
        request.user,
        ShoppingList.objects.filter(family=family, archived=False),
    ).order_by("sort_order", "created_at")
    if not raw_id:
        target = rows.first() if use_default else None
        return str(target.id) if target else None
    target = rows.filter(id=raw_id).first()
    if not target:
        raise PermissionDenied("Einkaufsliste nicht gefunden.")
    return str(target.id)


def _prediction_target(request, family):
    list_id = _visible_list_id(request, family, request.data.get("list"), use_default=True)
    if list_id:
        return list_id
    target = ShoppingList.objects.create(family=family, name="Einkauf", icon="cart-shopping")
    set_shopping_access(target, actor=request.user, visibility="family", allow_initialize=True)
    return str(target.id)


@api_view(["GET"])
def shopping_prediction_list(request):
    family = _family(request)
    list_id = _visible_list_id(request, family, request.query_params.get("list"))
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
        with transaction.atomic():
            list_id = _prediction_target(request, family)
            item, created = accept_shopping_prediction(
                family,
                key,
                request.user,
                list_id=list_id,
            )
            if not can_access_shopping_list(request.user, item.shopping_list):
                raise ValueError("Dieser Vorschlag ist nicht mehr aktuell.")
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
        with transaction.atomic():
            list_id = _prediction_target(request, family)
            items = accept_all_shopping_predictions(
                family,
                request.user,
                list_id=list_id,
            )
            if any(not can_access_shopping_list(request.user, item.shopping_list) for item in items):
                raise ValueError("Ein Vorschlag ist nicht mehr aktuell.")
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
