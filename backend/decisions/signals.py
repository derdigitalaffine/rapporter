from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from games.models import GameMatch

from .tiebreaks import resolve_game_tie_break


@receiver(post_save, sender=GameMatch, dispatch_uid="decisions.resolve_game_tie_break")
def resolve_finished_game_tie_break(sender, instance, **kwargs):
    if instance.status != GameMatch.Status.FINISHED:
        return
    with transaction.atomic():
        locked = GameMatch.objects.select_for_update().get(id=instance.id)
        resolve_game_tie_break(locked)
