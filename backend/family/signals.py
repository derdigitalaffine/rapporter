from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .domain_notifications import notify_domain_event
from .memory import remember_entry
from .models import FamilyEvent, InboxItem, Membership, RoutineLog, ShoppingItem, ShoppingList, Task, TaskList
from .request_context import current_actor, current_path, mark_notification_once


def _previous(instance, model, fields):
    if not instance.pk:return None
    return model.objects.filter(pk=instance.pk).values(*fields).first()

def _system_request():
    path=current_path();return "/automation-rules/" in path or "/integration-hub/" in path or "/integrations/" in path

def _member_name(membership):return membership.display_name or membership.user.get_short_name() or membership.user.username

@receiver(pre_save,sender=Task)
def task_before_save(sender,instance,**kwargs):instance._notification_previous=_previous(instance,Task,["title","notes","due_at","completed_at","assignee_id","task_list_id","priority"])
@receiver(post_save,sender=Task)
def task_after_save(sender,instance,created,**kwargs):
    if instance.birthday_context:
        from .models import BirthdayGiftPlan
        plans=BirthdayGiftPlan.objects.filter(linked_task=instance)
        if instance.completed_at:plans.exclude(status="given").update(status="ready")
        else:plans.filter(status="ready").update(status="planned")
        return
    remember_entry(instance,bump=created);actor=current_actor() or (instance.created_by if created else None)
    if not actor or str(instance.source).startswith("rule:"):return
    context={"item":instance.title,"task_id":instance.id,"list_id":instance.task_list_id,"list":instance.task_list.name if instance.task_list_id else "Aufgaben"}
    if created:
        if instance.assignee_id:notify_domain_event(instance.family,"task.assigned",actor=actor,context=context,target_users=[instance.assignee_id])
        notify_domain_event(instance.family,"task.created",actor=actor,context=context,exclude_users=[instance.assignee_id] if instance.assignee_id else None);return
    previous=getattr(instance,"_notification_previous",None) or {}
    if previous.get("completed_at")!=instance.completed_at:notify_domain_event(instance.family,"task.completed" if instance.completed_at else "task.reopened",actor=actor,context=context)
    if previous.get("assignee_id")!=instance.assignee_id and instance.assignee_id:notify_domain_event(instance.family,"task.assigned",actor=actor,context=context,target_users=[instance.assignee_id])
    if any(previous.get(field)!=getattr(instance,field) for field in ["title","notes","due_at","task_list_id","priority"]):
        targets=[value for value in {previous.get("assignee_id"),instance.assignee_id} if value];notify_domain_event(instance.family,"task.updated",actor=actor,context=context,target_users=targets or None)

@receiver(post_save,sender=TaskList)
def task_list_after_save(sender,instance,created,**kwargs):
    actor=current_actor()
    if created and actor and not _system_request():notify_domain_event(instance.family,"task.list.created",actor=actor,context={"list":instance.name,"list_id":instance.id})
@receiver(post_save,sender=ShoppingList)
def shopping_list_after_save(sender,instance,created,**kwargs):
    actor=current_actor()
    if created and actor and not _system_request():notify_domain_event(instance.family,"shopping.list.created",actor=actor,context={"list":instance.name,"list_id":instance.id})
@receiver(pre_save,sender=ShoppingItem)
def shopping_item_before_save(sender,instance,**kwargs):instance._notification_previous=_previous(instance,ShoppingItem,["name","quantity","category","note","aisle","checked","shopping_list_id"])
@receiver(post_save,sender=ShoppingItem)
def shopping_item_after_save(sender,instance,created,**kwargs):
    if instance.birthday_context:return
    remember_entry(instance,bump=created);actor=current_actor() or (instance.added_by if created else None)
    if not actor or _system_request() or (created and instance.added_by_id and instance.added_by_id!=actor.id):return
    context={"item":instance.name,"item_id":instance.id,"list":instance.shopping_list.name,"list_id":instance.shopping_list_id,"previous_checked":(getattr(instance,"_notification_previous",None) or {}).get("checked")}
    if created:notify_domain_event(instance.shopping_list.family,"shopping.item.created",actor=actor,context=context);return
    previous=getattr(instance,"_notification_previous",None) or {}
    if previous.get("checked")!=instance.checked:notify_domain_event(instance.shopping_list.family,"shopping.item.completed" if instance.checked else "shopping.item.reopened",actor=actor,context=context)
    elif any(previous.get(field)!=getattr(instance,field) for field in ["name","quantity","category","note","aisle","shopping_list_id"]):notify_domain_event(instance.shopping_list.family,"shopping.item.updated",actor=actor,context=context)
@receiver(post_delete,sender=ShoppingItem)
def shopping_item_after_delete(sender,instance,**kwargs):
    actor=current_actor();path=current_path()
    if not actor or "/smart/shopping-lists/" not in path:return
    key=f"shopping.items.cleared:{instance.shopping_list_id}"
    if not mark_notification_once(key):return
    shopping=ShoppingList.objects.filter(id=instance.shopping_list_id).select_related("family").first()
    if shopping:notify_domain_event(shopping.family,"shopping.items.cleared",actor=actor,context={"list":shopping.name,"list_id":shopping.id})
@receiver(pre_save,sender=FamilyEvent)
def family_event_before_save(sender,instance,**kwargs):instance._notification_previous=_previous(instance,FamilyEvent,["title","starts_at","ends_at","payload","type","source_id"])
@receiver(post_save,sender=FamilyEvent)
def family_event_after_save(sender,instance,created,**kwargs):
    actor=current_actor()
    if not actor or instance.source_id or instance.type!="calendar.event":return
    context={"item":instance.title,"event_id":instance.id}
    if created:notify_domain_event(instance.family,"calendar.event.created",actor=actor,context=context);return
    previous=getattr(instance,"_notification_previous",None) or {}
    if any(previous.get(field)!=getattr(instance,field) for field in ["title","starts_at","ends_at","payload"]):notify_domain_event(instance.family,"calendar.event.updated",actor=actor,context=context)
@receiver(pre_delete,sender=FamilyEvent)
def family_event_before_delete(sender,instance,**kwargs):
    actor=current_actor()
    if actor and not instance.source_id and instance.type=="calendar.event":notify_domain_event(instance.family,"calendar.event.deleted",actor=actor,context={"item":instance.title})
@receiver(post_save,sender=RoutineLog)
def routine_log_after_save(sender,instance,created,**kwargs):
    actor=current_actor() or instance.done_by
    if created and actor:notify_domain_event(instance.routine.family,"routine.completed",actor=actor,context={"item":instance.routine.name,"routine_id":instance.routine_id})
@receiver(pre_save,sender=Membership)
def membership_before_save(sender,instance,**kwargs):instance._notification_previous=_previous(instance,Membership,["role","display_name"])
@receiver(post_save,sender=Membership)
def membership_after_save(sender,instance,created,**kwargs):
    actor=current_actor() or (instance.user if created else None)
    if created:notify_domain_event(instance.family,"family.member.joined",actor=actor,context={"member":_member_name(instance)},exclude_users=[instance.user_id]);return
    previous=getattr(instance,"_notification_previous",None) or {}
    if actor and previous.get("role")!=instance.role:notify_domain_event(instance.family,"family.member.updated",actor=actor,context={"member":_member_name(instance),"role":instance.get_role_display()})
@receiver(pre_delete,sender=Membership)
def membership_before_delete(sender,instance,**kwargs):
    actor=current_actor()
    if actor:notify_domain_event(instance.family,"family.member.removed",actor=actor,context={"member":_member_name(instance)},exclude_users=[instance.user_id])
@receiver(post_save,sender=InboxItem)
def inbox_after_save(sender,instance,created,**kwargs):
    actor=current_actor()
    # Manual family messages resolve their explicit recipient set in FamilyMessageViewSet.
    if created and actor and instance.source not in {"automation","manual_message"} and not _system_request():notify_domain_event(instance.family,"inbox.created",actor=actor,context={"item":instance.title,"inbox_id":instance.id})
