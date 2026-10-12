from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ShoppingItem, ShoppingList
from .serializers import ShoppingItemSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def shopping_reorder(request, list_id):
    item_ids = request.data.get("item_ids")
    if not isinstance(item_ids, list) or not item_ids:
        return Response({"item_ids": "Eine vollständige Artikelfolge ist erforderlich."}, status=status.HTTP_400_BAD_REQUEST)
    normalized = [str(value) for value in item_ids]
    if len(normalized) != len(set(normalized)):
        return Response({"item_ids": "Artikel dürfen nur einmal vorkommen."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        shopping_list = ShoppingList.objects.select_for_update().filter(
            id=list_id,
            family__memberships__user=request.user,
        ).first()
        if not shopping_list:
            return Response({"detail": "Einkaufsliste nicht gefunden."}, status=status.HTTP_404_NOT_FOUND)

        all_rows = list(shopping_list.items.select_for_update().order_by("position", "created_at", "id"))
        visible = [item for item in all_rows if item.hidden_from_user_id != request.user.id]
        visible_by_id = {str(item.id): item for item in visible}
        if set(normalized) != set(visible_by_id):
            return Response({"item_ids": "Die Reihenfolge muss alle sichtbaren Artikel dieser Liste enthalten."}, status=status.HTTP_400_BAD_REQUEST)

        visible_queue = [visible_by_id[item_id] for item_id in normalized]
        queue_index = 0
        merged = []
        for item in all_rows:
            if item.hidden_from_user_id == request.user.id:
                merged.append(item)
            else:
                merged.append(visible_queue[queue_index])
                queue_index += 1

        changed_at = timezone.now()
        for index, item in enumerate(merged, start=1):
            item.position = index * 1000
            item.updated_at = changed_at
        ShoppingItem.objects.bulk_update(merged, ["position", "updated_at"])

    ordered_visible = [item for item in merged if item.hidden_from_user_id != request.user.id]
    return Response(ShoppingItemSerializer(ordered_visible, many=True, context={"request": request}).data)
