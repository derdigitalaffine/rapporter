from django.db.models.signals import post_save
from django.dispatch import receiver

from family.models import InboxItem
from .legacy_bridge import schedule_inbox_mirror


@receiver(post_save, sender=InboxItem, dispatch_uid='messenger.mirror_family_inbox')
def mirror_family_inbox(sender, instance, created, **kwargs):
    if created:
        schedule_inbox_mirror(instance.pk)
