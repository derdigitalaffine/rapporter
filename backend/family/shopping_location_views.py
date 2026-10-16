from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Family, Membership, ShoppingList
from .shopping_access import visible_shopping_lists
from .shopping_geocoder import ShoppingGeocoderError, attribution, reverse_store, search_stores
from .shopping_models import ShoppingListStoreProfile, ShoppingStore


def _family_for_user(user, family_id):
    family = Family.objects.filter(id=family_id, status=Family.Status.ACTIVE).first()
    if not family or not Membership.objects.filter(family=family, user=user).exists():
        return None
    return family


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _coordinate(value, minimum, maximum):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if minimum <= number <= maximum else None


def _store_payload(store):
    return {
        "id": str(store.id),
        "family": str(store.family_id),
        "name": store.name,
        "branch_label": store.branch_label,
        "display_label": store.display_label,
        "address": store.address,
        "location_provider": store.location_provider,
        "location_ref": store.location_ref,
        "latitude": str(store.latitude) if store.latitude is not None else None,
        "longitude": str(store.longitude) if store.longitude is not None else None,
        "active": store.active,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shopping_store_location_lookup(request):
    if not getattr(settings, "SHOPPING_STORE_AUTOCOMPLETE_ENABLED", True):
        return Response({"code": "store_lookup_disabled"}, status=status.HTTP_404_NOT_FOUND)
    family = _family_for_user(request.user, request.query_params.get("family"))
    if not family:
        return Response({"detail": "Familie nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)

    mode = str(request.query_params.get("mode") or "search").strip().lower()
    try:
        if mode == "search":
            results = search_stores(request.query_params.get("q"))
        elif mode == "reverse":
            results = reverse_store(request.query_params.get("lat"), request.query_params.get("lon"))
        else:
            return Response({"mode": "Ungültiger Standortmodus."}, status=status.HTTP_400_BAD_REQUEST)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except ShoppingGeocoderError:
        return Response(
            {"code": "store_lookup_unavailable", "detail": "Filialsuche ist gerade nicht verfügbar."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"results": results, "attribution": attribution()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def shopping_store_location_resolve(request):
    family = _family_for_user(request.user, request.data.get("family"))
    if not family:
        return Response({"detail": "Familie nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    shopping_list = visible_shopping_lists(
        request.user,
        ShoppingList.objects.filter(id=request.data.get("shopping_list"), family=family, archived=False),
    ).first()
    if not shopping_list:
        return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)

    provider = _clean(request.data.get("provider"), 32).lower()
    provider_ref = _clean(request.data.get("provider_ref"), 160)
    name = _clean(request.data.get("name"), 120)
    branch_label = _clean(request.data.get("branch_label"), 120)
    address = _clean(request.data.get("address"), 240)
    latitude = _coordinate(request.data.get("latitude"), Decimal("-90"), Decimal("90"))
    longitude = _coordinate(request.data.get("longitude"), Decimal("-180"), Decimal("180"))
    if provider != "nominatim" or not provider_ref or not name or latitude is None or longitude is None:
        return Response({"detail": "Ungültiger Filialtreffer."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        store, created = ShoppingStore.objects.get_or_create(
            family=family,
            location_provider=provider,
            location_ref=provider_ref,
            defaults={
                "name": name,
                "branch_label": branch_label,
                "address": address,
                "latitude": latitude,
                "longitude": longitude,
                "created_by": request.user,
            },
        )
        update_fields = []
        if not store.active:
            store.active = True
            update_fields.append("active")
        # Keep family-authored labels intact; only fill provider metadata that was blank.
        for field, value in (("address", address), ("latitude", latitude), ("longitude", longitude)):
            if not getattr(store, field) and value:
                setattr(store, field, value)
                update_fields.append(field)
        if update_fields:
            store.save(update_fields=[*update_fields, "updated_at"])
        ShoppingListStoreProfile.objects.update_or_create(shopping_list=shopping_list, defaults={"store": store})
        ShoppingList.objects.filter(pk=shopping_list.pk).update(store=store.display_label)

    return Response({"store": _store_payload(store), "created": created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
