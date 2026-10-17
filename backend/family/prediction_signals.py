from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .memory import normalize_name
from .models import ShoppingItem, ShoppingPurchaseEvent
from .request_context import current_actor
from .shopping_models import ShoppingListAccess, ShoppingListStoreProfile
from .shopping_purchase_context_models import ShoppingPurchaseStoreContext


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
    shopping_list = instance.shopping_list
    try:
        access = shopping_list.access_settings
    except ShoppingListAccess.DoesNotExist:
        access = None
    # ShoppingPurchaseEvent feeds family-wide prediction learning. Content from
    # private/selected lists must never enter that shared pool.
    if access and access.visibility != ShoppingListAccess.Visibility.FAMILY:
        return
    name = (instance.name or "").strip()
    normalized = normalize_name(name)
    if not normalized:
        return
    actor = current_actor() or instance.added_by
    assignment = (
        ShoppingListStoreProfile.objects.select_related("store")
        .filter(shopping_list=shopping_list)
        .first()
    )
    store = assignment.store if assignment else None
    store_label = store.display_label if store else (shopping_list.store or "")
    purchase_event, event_created = ShoppingPurchaseEvent.objects.get_or_create(
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
            # Keep the display label as an immutable history snapshot. The
            # canonical id is stored separately and may later become NULL when a
            # shopping place is deleted.
            "store": store_label,
            "purchased_by": actor,
        },
    )
    if event_created:
        ShoppingPurchaseStoreContext.objects.create(
            purchase_event=purchase_event,
            shopping_store=store,
            address_snapshot=(store.address if store else ""),
        )
