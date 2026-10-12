from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Membership, ShoppingItem, ShoppingList
from .serializers import ShoppingItemSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def shopping_reorder(request, list_id):
    shopping_list = ShoppingList.objects.filter(id=list_id, family__memberships__user=request.user).first()
    if not shopping_list:
        return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)
    if not Membership.objects.filter(family=shopping_list.family, user=request.user).exists():
        return Response({"detail": "Kein Zugriff auf diese Einkaufsliste."}, status=status.HTTP_403_FORBIDDEN)

    item_ids = request.data.get("item_ids")
    if not isinstance(item_ids, list) or not item_ids:
        return Response({"item_ids": "Eine vollständige Artikelfolge ist erforderlich."}, status=status.HTTP_400_BAD_REQUEST)
    normalized = [str(value) for value in item_ids]
    if len(normalized) != len(set(normalized)):
        return Response({"item_ids": "Artikel dürfen nur einmal vorkommen."}, status=status.HTTP_400_BAD_REQUEST)

    visible = list(shopping_list.items.exclude(hidden_from_user=request.user).order_by("position", "created_at", "id"))
    visible_by_id = {str(item.id): item for item in visible}
    if set(normalized) != set(visible_by_id):
        return Response({"item_ids": "Die Reihenfolge muss alle sichtbaren Artikel dieser Liste enthalten."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
        rows = []
        for index, item_id in enumerate(normalized, start=1):
            item = visible_by_id[item_id]
            item.position = index * 1000
            rows.append(item)
        ShoppingItem.objects.bulk_update(rows, ["position", "updated_at"])

    ordered = sorted(rows, key=lambda item: (item.position, item.created_at, str(item.id)))
    return Response(ShoppingItemSerializer(ordered, many=True, context={"request": request}).data)
