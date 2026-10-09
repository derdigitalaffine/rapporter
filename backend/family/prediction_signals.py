from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .memory import normalize_name
from .models import RoutineLog, ShoppingItem
from .models_features import PredictionFeedback, ShoppingPurchaseEvent


@receiver(post_save,sender=ShoppingItem)
def capture_purchase(sender,instance,created,**kwargs):
    previous=getattr(instance,"_notification_previous",None) or {}
    became_checked=instance.checked and (created or previous.get("checked") is False)
    if not became_checked:return
    normalized=normalize_name(instance.name)
    if not normalized:return
    ShoppingPurchaseEvent.objects.create(family=instance.shopping_list.family,normalized_name=normalized,name=instance.name,quantity=instance.quantity,category=instance.category,purchased_at=instance.checked_at or timezone.now(),source_item_id=instance.id)
    PredictionFeedback.objects.filter(family=instance.shopping_list.family,kind=PredictionFeedback.Kind.SHOPPING,subject_key=normalized).update(dismissed=False,snoozed_until=None)


@receiver(post_save,sender=RoutineLog)
def reset_routine_prediction_feedback(sender,instance,created,**kwargs):
    if created:PredictionFeedback.objects.filter(family=instance.routine.family,kind=PredictionFeedback.Kind.ROUTINE,subject_key=str(instance.routine_id)).update(dismissed=False,snoozed_until=None)
