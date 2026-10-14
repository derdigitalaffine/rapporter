"""Consume canonical successful mutation events, never derive actor from assignee."""
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from family.models import Task, Routine, RoutineLog, ShoppingItem, ShoppingList, ShoppingPurchaseEvent, Membership, Family
from family.request_context import current_actor
from family.unified_action_models import ActionDomainEvent, ActionCompletion
from .models import FamilyContributionEvent as Event
from .services import record, remove_entity, recompute, task_completion_key, task_effort


def public_task(task):
    return task and not task.hidden_from_user_id and not task.birthday_context


def event_key(row):
    if row.completion_id:
        if row.completion.legacy_log_id:
            return f"routine-log:{row.completion.legacy_log_id}"
        return task_completion_key(row.action.legacy_task_id, row.completion.occurred_at)
    return f"action-event:{row.id}"


def action_event(row):
    action = row.action
    obj = action.legacy_task or action.legacy_routine
    if not obj or (action.legacy_task_id and not public_task(obj)):
        return
    verb = {"action.created": "created", "action.completed": "completed", "action.reopened": "reopened"}.get(row.event_type)
    if not verb or (action.kind_hint == "routine" and verb == "reopened"):
        return
    completion = row.completion
    actor = completion.actor if completion and verb == "completed" else row.actor
    if verb == "created" and not actor and action.legacy_task_id:
        actor = obj.created_by
    when = completion.occurred_at if completion and verb == "completed" else row.created_at
    effort = task_effort(obj) if action.legacy_task_id and verb == "completed" else None
    record(family=obj.family, domain=action.kind_hint, action=verb, entity_type=action.kind_hint,
        entity_id=obj.id, occurred_at=when, actor=actor, effort_minutes=effort,
        source="automation" if action.source.startswith("rule:") else "ui", idempotency_key=event_key(row))


@receiver(post_save, sender=ActionDomainEvent)
def on_action_event(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        action_event(instance)


@receiver(post_save, sender=ActionCompletion)
def on_completion_update(sender, instance, created, raw=False, **kwargs):
    # Unified commands finalize the reliable actor after the legacy mirror signal.
    if not created and not raw:
        rows = instance.action.domain_events.filter(completion=instance, event_type="action.completed")
        from django.db import transaction
        for row in rows:
            with transaction.atomic():
                family = Family.objects.select_for_update().get(pk=instance.action.family_id)
                membership = Membership.objects.filter(family=family, user=instance.actor).first() if instance.actor_id else None
                changed = Event.objects.filter(family=family, idempotency_key=event_key(row), attribution_finalized=False, created_at__gte=timezone.now()-timedelta(minutes=5)).exclude(actor_membership=membership).update(actor_user=instance.actor if membership else None, actor_membership=membership, attribution_finalized=True)
                if changed:
                    recompute(family)


@receiver(post_save, sender=ShoppingItem)
def on_item(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    if instance.hidden_from_user_id or instance.birthday_context:
        remove_entity(instance.shopping_list.family_id, "shopping_item", instance.id)
    elif created:
        record(family=instance.shopping_list.family, domain="shopping", action="item_added", entity_type="shopping_item",
            entity_id=instance.id, occurred_at=instance.created_at, actor=current_actor() or instance.added_by,
            idempotency_key=f"shopping-added:{instance.id}")


def purchase_event(instance):
    item = ShoppingItem.objects.filter(pk=instance.source_item_id).first()
    # Deleted historical rows cannot prove gift ACL; skip rather than reconstruct.
    if not item or item.hidden_from_user_id or item.birthday_context:
        return
    record(family=instance.family, domain="shopping", action="item_purchased", entity_type="shopping_item",
        entity_id=item.id, occurred_at=instance.purchased_at, actor=instance.purchased_by,
        idempotency_key=f"shopping-purchase:{instance.id}", source="import" if not current_actor() else "ui")


@receiver(post_save, sender=ShoppingPurchaseEvent)
def on_purchase(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        purchase_event(instance)


@receiver(post_save, sender=ShoppingList)
def on_list(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        record(family=instance.family, domain="shopping", action="list_created", entity_type="shopping_list",
            entity_id=instance.id, occurred_at=instance.created_at, actor=current_actor(), idempotency_key=f"shopping-list:{instance.id}")


@receiver(post_save, sender=Task)
def on_task_visibility(sender, instance, raw=False, **kwargs):
    if not raw and not public_task(instance):
        remove_entity(instance.family_id, "task", instance.id)


@receiver(pre_delete, sender=Task)
@receiver(pre_delete, sender=Routine)
@receiver(pre_delete, sender=ShoppingItem)
def on_entity_delete(sender, instance, **kwargs):
    kind = {Task: "task", Routine: "routine", ShoppingItem: "shopping_item"}[sender]
    family_id = instance.shopping_list.family_id if sender is ShoppingItem else instance.family_id
    remove_entity(family_id, kind, instance.id)


@receiver(pre_delete, sender=RoutineLog)
def on_log_delete(sender, instance, **kwargs):
    # Undo removes that execution from statistics while retaining canonical history.
    family = instance.routine.family
    event_ids = ActionDomainEvent.objects.filter(completion__legacy_log=instance).values_list("id", flat=True)
    keys = [f"routine-log:{instance.pk}"]
    if Event.objects.filter(family=family, idempotency_key__in=keys).exists():
        Event.objects.filter(family=family, idempotency_key__in=keys).delete()
        recompute(family)


@receiver(pre_delete, sender=Membership)
def on_member_delete(sender, instance, **kwargs):
    Event.objects.filter(actor_membership=instance).update(actor_membership=None, actor_user=None, attribution_finalized=True)
    # Recompute before FK deletion so named daily buckets disappear immediately.
    recompute(instance.family)


@receiver(pre_save, sender=Family)
def before_timezone_change(sender, instance, raw=False, **kwargs):
    instance._statistics_previous_timezone = Family.objects.filter(pk=instance.pk).values_list("timezone", flat=True).first() if not raw else None


@receiver(post_save, sender=Family)
def on_timezone_change(sender, instance, created, raw=False, **kwargs):
    if not created and not raw and getattr(instance, "_statistics_previous_timezone", instance.timezone) != instance.timezone:
        recompute(instance)
