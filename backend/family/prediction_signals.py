from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .memory import normalize_name
from .models import ShoppingItem, ShoppingPurchaseEvent
from .request_context import current_actor


@receiver(pre_save, sender=ShoppingItem)
def shopping_item_purchase_before_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._purchase_previous_checked = False
        return
    previous = ShoppingItem.objects.filter(pk=instance.pk).values("checked").first()
    instance._purchase_previous_checked = bool(previous and previous["checked"])


@receiver(post_save, sender=ShoppingItem)
def shopping_item_purchase_after_save(sender, instance, created, **kwargs):
    if instance.birthday_context:
        return
    was_checked = False if created else bool(getattr(instance, "_purchase_previous_checked", False))
    if was_checked or not instance.checked or not instance.checked_at:
        return
    name = (instance.name or "").strip()
    normalized = normalize_name(name)
    if not normalized:
        return
    shopping_list = instance.shopping_list
    actor = current_actor() or instance.added_by
    ShoppingPurchaseEvent.objects.get_or_create(
        source_item_id=instance.id,
        purchased_at=instance.checked_at,
        defaults={
            "family": shopping_list.family,
            "shopping_list": shopping_list,
            "normalized_name": normalized,
            "display_name": name,
            "quantity": instance.quantity or "",
            "category": instance.category or "",
            "aisle": instance.aisle or "",
            "store": shopping_list.store or "",
            "purchased_by": actor,
        },
    )
