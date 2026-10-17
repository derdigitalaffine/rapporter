from rest_framework.exceptions import PermissionDenied

from .shopping_access import can_manage_shopping_access
from .shopping_access_views import ShoppingListViewSet as AccessShoppingListViewSet


class ShoppingListViewSet(AccessShoppingListViewSet):
    """Shopping list endpoint with destructive operations limited to managers."""

    def perform_destroy(self, instance):
        if not can_manage_shopping_access(self.request.user, instance):
            raise PermissionDenied("Du kannst diese Einkaufsliste nicht löschen.")
        super().perform_destroy(instance)
