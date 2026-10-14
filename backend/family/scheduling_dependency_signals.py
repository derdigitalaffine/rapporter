from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import FamilyEvent
from .scheduling_models import SchedulingDependency, SchedulingSeries
from .unified_action_models import Action


def _refresh(family_id, anchor_type, anchor_id):
    from .models import Family
    from .scheduling_dependencies import refresh_anchor_dependencies

    family = Family.objects.filter(id=family_id).first()
    if family is not None:
        refresh_anchor_dependencies(family, anchor_type, anchor_id)


def _schedule_refresh(instance, anchor_type):
    family_id = instance.family_id
    anchor_id = instance.id
    transaction.on_commit(lambda: _refresh(family_id, anchor_type, anchor_id))


@receiver(post_save, sender=FamilyEvent)
def event_dependency_refresh(sender, instance, **kwargs):
    if SchedulingDependency.objects.filter(
        family_id=instance.family_id,
        anchor_type=SchedulingSeries.TargetType.EVENT,
        anchor_id=instance.id,
        enabled=True,
    ).exists():
        _schedule_refresh(instance, SchedulingSeries.TargetType.EVENT)


@receiver(post_save, sender=Action)
def action_dependency_refresh(sender, instance, **kwargs):
    if SchedulingDependency.objects.filter(
        family_id=instance.family_id,
        anchor_type=SchedulingSeries.TargetType.ACTION,
        anchor_id=instance.id,
        enabled=True,
    ).exists():
        _schedule_refresh(instance, SchedulingSeries.TargetType.ACTION)


@receiver(post_delete, sender=FamilyEvent)
def event_dependency_orphan(sender, instance, **kwargs):
    SchedulingDependency.objects.filter(
        family_id=instance.family_id,
        anchor_type=SchedulingSeries.TargetType.EVENT,
        anchor_id=instance.id,
    ).update(enabled=False)


@receiver(post_delete, sender=Action)
def action_dependency_orphan(sender, instance, **kwargs):
    SchedulingDependency.objects.filter(
        family_id=instance.family_id,
        anchor_type=SchedulingSeries.TargetType.ACTION,
        anchor_id=instance.id,
    ).update(enabled=False)
