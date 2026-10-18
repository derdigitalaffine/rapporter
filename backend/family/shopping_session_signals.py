from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ShoppingItem
from .request_context import current_actor
from .shopping_models import ShoppingSessionActivity
from .shopping_session_service import record_shopping_item_activity


@receiver(post_save, sender=ShoppingItem)
def shopping_session_item_activity(sender, instance, created, **kwargs):
    if instance.birthday_context or instance.hidden_from_user_id:
        return
    actor = current_actor() or (instance.added_by if created else None)
    if not actor:
        return
    if created:
        kind = ShoppingSessionActivity.Kind.ITEM_ADDED
    else:
        previous = getattr(instance, "_notification_previous", None) or {}
        if previous.get("checked") == instance.checked:
            return
        kind = (
            ShoppingSessionActivity.Kind.ITEM_CHECKED
            if instance.checked
            else ShoppingSessionActivity.Kind.ITEM_REOPENED
        )
    record_shopping_item_activity(
        instance,
        kind,
        actor,
        client_activity=getattr(instance, "_shopping_client_activity", None),
    )
