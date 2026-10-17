from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ShoppingList
from .shopping_access import visible_shopping_lists
from .shopping_access_views import (
    ShoppingItemViewSet as AccessShoppingItemViewSet,
    ShoppingStoreViewSet as AccessShoppingStoreViewSet,
)
from .shopping_learned_order import learned_order_for_store
from .shopping_models import ShoppingSessionActivity
from .shopping_session_service import record_shopping_item_activity


class ShoppingItemViewSet(AccessShoppingItemViewSet):
    """Canonical item viewset with replay-safe shopping activity metadata."""

    def perform_update(self, serializer):
        was_checked = serializer.instance.checked
        super().perform_update(serializer)
        item = serializer.instance
        if item.checked == was_checked:
            return
        kind = (
            ShoppingSessionActivity.Kind.ITEM_CHECKED
            if item.checked
            else ShoppingSessionActivity.Kind.ITEM_REOPENED
        )
        record_shopping_item_activity(
            item,
            kind,
            self.request.user,
            client_activity=self.request.data.get("client_activity"),
        )


class ShoppingStoreViewSet(AccessShoppingStoreViewSet):
    @action(detail=True, methods=["get"], url_path="learned-order")
    def learned_order(self, request, pk=None):
        store = self.get_object()
        list_id = request.query_params.get("shopping_list")
        shopping_list = visible_shopping_lists(
            request.user,
            ShoppingList.objects.filter(family=store.family, archived=False),
        ).filter(id=list_id).first()
        if not shopping_list:
            return Response(
                {"detail": "Einkaufsliste nicht gefunden."},
                status=status.HTTP_404_NOT_FOUND,
            )
        items = (
            shopping_list.items.exclude(hidden_from_user=request.user)
            .filter(birthday_context__isnull=True)
            .order_by("position", "created_at", "id")
        )
        return Response(learned_order_for_store(store, items))
