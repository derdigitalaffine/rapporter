from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

from family.models import ShoppingItem
from .commitment_models import BudgetCommitment


@receiver(pre_delete, sender=ShoppingItem, dispatch_uid="expenses_release_shopping_budget_commitment")
def release_deleted_shopping_commitment(sender, instance, **kwargs):
    """A deleted plan must stop reserving money, but its finance history remains."""
    BudgetCommitment.objects.filter(
        family=instance.shopping_list.family,
        source_type="shopping_item",
        source_id=instance.id,
        status=BudgetCommitment.Status.ACTIVE,
    ).update(
        status=BudgetCommitment.Status.RELEASED,
        released_at=timezone.now(),
        updated_at=timezone.now(),
    )
