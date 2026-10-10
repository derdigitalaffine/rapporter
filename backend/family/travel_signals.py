from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import FamilyEvent
from .private_images import remove_image
from .travel_models import Trip, TripPhoto


@receiver(post_delete, sender=TripPhoto)
def cleanup_trip_photo(sender, instance, **kwargs):
    transaction.on_commit(lambda: remove_image(instance.key))


@receiver(post_delete, sender=Trip)
def cleanup_trip_calendar_event(sender, instance, **kwargs):
    event_id = instance.calendar_event_id
    if event_id:
        transaction.on_commit(lambda: FamilyEvent.objects.filter(pk=event_id, type="travel.trip").delete())
