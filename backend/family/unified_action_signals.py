from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from .models import Task, Routine, RoutineLog
from .unified_action_models import Action, ActionCompletion
from .unified_action_service import mirror, observe_task, observe_log

@receiver(pre_save, sender=Task)
def before_task(sender, instance, **kwargs):
    instance._action_previous = Task.objects.filter(pk=instance.pk).values('completed_at').first()

@receiver(post_save, sender=Task)
def after_task(sender, instance, **kwargs):
    observe_task(instance, getattr(instance, '_action_previous', None))

@receiver(post_save, sender=Routine)
def after_routine(sender, instance, **kwargs):
    mirror(instance)

@receiver(post_save, sender=RoutineLog)
def after_log(sender, instance, **kwargs):
    observe_log(instance)

@receiver(pre_delete, sender=RoutineLog)
def before_log_delete(sender, instance, **kwargs):
    ActionCompletion.objects.filter(legacy_log=instance, undone_at__isnull=True).update(undone_at=timezone.now())

@receiver(pre_delete, sender=Task)
@receiver(pre_delete, sender=Routine)
def before_legacy_delete(sender, instance, **kwargs):
    Action.objects.filter(**{'legacy_task' if sender is Task else 'legacy_routine': instance}).update(state='archived')
