from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .private_images import remove_image
from .travel_models import TripPhoto


@receiver(post_delete, sender=TripPhoto)
def cleanup_trip_photo(sender, instance, **kwargs):
    transaction.on_commit(lambda: remove_image(instance.key))
