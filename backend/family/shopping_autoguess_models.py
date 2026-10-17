from django.db import models

from .models import ShoppingItem, ShoppingList, TimestampedModel


class ShoppingItemCreateReceipt(TimestampedModel):
    """Technical idempotency receipt for explicit ShoppingItem creates.

    The mutation id is scoped to the canonical target list. Product names are
    deliberately not part of idempotency: two explicit same-name adds remain
    two items, while replaying one mutation returns the original item.
    """

    shopping_list = models.ForeignKey(
        ShoppingList,
        on_delete=models.CASCADE,
        related_name="item_create_receipts",
    )
    mutation_id = models.UUIDField()
    item = models.OneToOneField(
        ShoppingItem,
        on_delete=models.CASCADE,
        related_name="create_receipt",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["shopping_list", "mutation_id"],
                name="shop_item_create_mutation_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["shopping_list", "mutation_id"], name="shop_item_create_mut_idx"),
        ]
