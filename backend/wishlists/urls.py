from django.urls import path

from .views import (
    wishlist_action,
    wishlist_collection,
    wishlist_context,
    wishlist_detail,
    wishlist_item_collection,
    wishlist_item_detail,
    wishlist_reservation,
)

urlpatterns = [
    path("wishlists/", wishlist_collection, name="wishlist_collection"),
    path("wishlists/<uuid:wishlist_id>/", wishlist_detail, name="wishlist_detail"),
    path("wishlists/<uuid:wishlist_id>/items/", wishlist_item_collection, name="wishlist_item_collection"),
    path("wishlists/<uuid:wishlist_id>/context/", wishlist_context, name="wishlist_context"),
    path("wishlist-items/<uuid:item_id>/", wishlist_item_detail, name="wishlist_item_detail"),
    path("wishlist-items/<uuid:item_id>/reservation/", wishlist_reservation, name="wishlist_reservation"),
    path("wishlist-items/<uuid:item_id>/actions/", wishlist_action, name="wishlist_action"),
]
