import uuid

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import Family, ShoppingList
from .serializers import ShoppingItemSerializer
from .shopping_access import set_shopping_access, visible_shopping_lists
from .shopping_autoguess_models import ShoppingItemCreateReceipt


def _family_for_user(user, family_id):
    return Family.objects.filter(id=family_id, memberships__user=user).first()


def _parse_mutation_id(value):
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return False


@api_view(["POST"])
def shopping_quick_add(request):
    family = _family_for_user(request.user, request.data.get("family"))
    if not family:
        raise PermissionDenied()

    name = str(request.data.get("name") or "").strip()
    if not name:
        return Response({"detail": "Artikelname fehlt."}, status=status.HTTP_400_BAD_REQUEST)

    mutation_id = _parse_mutation_id(request.data.get("client_mutation_id"))
    if mutation_id is False:
        return Response({"client_mutation_id": ["Ungültige Mutation-ID."]}, status=status.HTTP_400_BAD_REQUEST)

    lists = visible_shopping_lists(request.user, ShoppingList.objects.filter(family=family, archived=False))
    shopping = None
    if request.data.get("shopping_list"):
        shopping = lists.filter(id=request.data["shopping_list"]).first()
        if not shopping:
            return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    shopping = shopping or lists.order_by("sort_order", "created_at").first()
    if not shopping:
        with transaction.atomic():
            shopping = ShoppingList.objects.create(family=family, name="Einkauf")
            set_shopping_access(shopping, actor=request.user, visibility="family", allow_initialize=True)

    with transaction.atomic():
        # Serialise create receipts per list so concurrent replays cannot both
        # pass the receipt lookup before the unique row exists.
        shopping = ShoppingList.objects.select_for_update().get(pk=shopping.pk)
        if mutation_id:
            receipt = (
                ShoppingItemCreateReceipt.objects.select_related("item")
                .filter(shopping_list=shopping, mutation_id=mutation_id)
                .first()
            )
            if receipt:
                return Response(
                    {
                        "item": ShoppingItemSerializer(receipt.item, context={"request": request}).data,
                        "reused": True,
                    },
                    status=status.HTTP_200_OK,
                )

        payload = {"shopping_list": str(shopping.id), "name": name}
        for field in ("quantity", "category", "aisle", "note", "favorite"):
            if field in request.data:
                payload[field] = request.data[field]

        serializer = ShoppingItemSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)
        item = serializer.save(added_by=request.user)
        if mutation_id:
            ShoppingItemCreateReceipt.objects.create(
                shopping_list=shopping,
                mutation_id=mutation_id,
                item=item,
            )

    return Response(
        {"item": ShoppingItemSerializer(item, context={"request": request}).data, "reused": False},
        status=status.HTTP_201_CREATED,
    )
