from django.db.models.signals import post_save
from django.dispatch import receiver

from .memory import remember_entry
from .models import ShoppingItem, Task


@receiver(post_save, sender=Task)
def remember_task(sender, instance, created, **kwargs):
    remember_entry(instance, bump=created)


@receiver(post_save, sender=ShoppingItem)
def remember_shopping_item(sender, instance, created, **kwargs):
    remember_entry(instance, bump=created)
