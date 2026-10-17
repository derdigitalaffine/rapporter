from django.db import models

from .models import ShoppingPurchaseEvent, TimestampedModel
from .shopping_models import ShoppingStore


class ShoppingPurchaseStoreContext(TimestampedModel):
    """Canonical shopping-place context captured for one immutable purchase event.

    ``ShoppingPurchaseEvent.store`` remains the immutable human-readable label
    snapshot used by legacy history. This sidecar adds the canonical store id and
    an address snapshot without rewriting old purchase events or guessing ids from
    legacy strings. Deleting a store therefore never erases historical context.
    """

    purchase_event = models.OneToOneField(
        ShoppingPurchaseEvent,
        on_delete=models.CASCADE,
        related_name="store_context",
    )
    shopping_store = models.ForeignKey(
        ShoppingStore,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_event_contexts",
    )
    address_snapshot = models.CharField(max_length=240, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["shopping_store", "created_at"],
                name="shop_purchase_store_idx",
            ),
        ]
