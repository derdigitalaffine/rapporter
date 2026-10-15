"""One transactional write boundary for synchronized ORM models.

A singleton row lock deliberately serializes the initial narrow sync scope. Unlike
sequence allocation alone, it makes journal cursors follow commit order. QuerySet
bulk operations use the same boundary; domain save hooks remain authoritative.
"""
from contextlib import contextmanager

from django.db import models, transaction
from django.db.models.signals import post_delete, m2m_changed

TYPES = {'ShoppingList': 'shopping_list', 'ShoppingItem': 'shopping_item',
         'TaskList': 'task_list', 'Task': 'task', 'FamilyEvent': 'event'}


@contextmanager
def sync_lock(using='default'):
    from .sync_models import SyncSequence
    with transaction.atomic(using=using):
        # Seeded by migration. Never use sequence allocation as a commit watermark.
        SyncSequence.objects.using(using).get_or_create(pk=1)
        SyncSequence.objects.using(using).select_for_update().get(pk=1)
        yield


def family_id(instance):
    return instance.shopping_list.family_id if type(instance).__name__ == 'ShoppingItem' else instance.family_id


def append_change(instance, operation, fields, using='default'):
    from .sync_models import SyncJournal, SyncSequence
    family = family_id(instance)
    seq = SyncSequence.objects.using(using).get(pk=1)
    seq.cursor += 1
    seq.save(update_fields=['cursor'])
    SyncJournal.objects.using(using).create(
        cursor=seq.cursor, family_id=family, entity_type=TYPES[type(instance).__name__],
        entity_id=instance.pk, operation=operation, version=instance.version,
        changed_fields=sorted(fields),
    )
    # Live transport is deliberately optional and emits only after commit.
    def wake():
        from django.conf import settings
        if getattr(settings, 'OFFLINE_LIVE_ENABLED', False):
            from .sync_live import publish
            publish(str(family), seq.cursor)
    transaction.on_commit(wake, using=using, robust=True)


def tracked_save(instance, save, args, kwargs):
    using = kwargs.get('using') or instance._state.db or 'default'
    with sync_lock(using):
        previous = type(instance).objects.using(using).filter(pk=instance.pk).values().first()
        fields = kwargs.get('update_fields')
        if fields is not None and not fields:
            return
        instance.version = (previous['version'] if previous else 0) + 1
        if fields is not None:
            kwargs['update_fields'] = set(fields) | {'version'}
        result = save(*args, **kwargs)
        current = type(instance).objects.using(using).filter(pk=instance.pk).values().get()
        changed = {f.name for f in instance._meta.concrete_fields
                   if f.name not in {'version', 'created_at', 'updated_at'}
                   and (previous is None or previous.get(f.attname) != current.get(f.attname))}
        append_change(instance, 'create' if previous is None else 'update', changed, using)
        return result


class SyncQuerySet(models.QuerySet):
    def select_for_update(self, **kwargs):
        # Preserve the same lock order for legacy workflow/REST writers that
        # explicitly lock a synchronized row before calling save().
        from .sync_models import SyncSequence
        SyncSequence.objects.using(self.db).get_or_create(pk=1)
        SyncSequence.objects.using(self.db).select_for_update().get(pk=1)
        return super().select_for_update(**kwargs)

    def update(self, **kwargs):
        # Resolve F/Case expressions in SQL, then use the normal domain save path.
        count = 0
        with sync_lock(self.db):
            for obj in self.select_for_update():
                expressions = {f'_sync_{i}': value for i, value in enumerate(kwargs.values()) if hasattr(value, 'resolve_expression')}
                evaluated = self.model.objects.using(self.db).filter(pk=obj.pk).annotate(**expressions).values(*expressions).get() if expressions else {}
                for i, (key, value) in enumerate(kwargs.items()):
                    setattr(obj, key, evaluated[f'_sync_{i}'] if hasattr(value, 'resolve_expression') else value)
                obj.save(using=self.db, update_fields=set(kwargs))
                count += 1
        return count

    def bulk_create(self, objs, **kwargs):
        if kwargs.get('ignore_conflicts') or kwargs.get('update_conflicts'):
            raise ValueError('Synchronized bulk creates require explicit conflict handling.')
        with sync_lock(self.db):
            for obj in objs:
                obj.save(using=self.db, force_insert=True)
        return objs

    def bulk_update(self, objs, fields, **kwargs):
        with sync_lock(self.db):
            for obj in objs:
                obj.save(using=self.db, update_fields=fields)
        return len(objs)

    def delete(self):
        with sync_lock(self.db):
            return super().delete()


def install_tracking():
    from .models import ShoppingList, ShoppingItem, TaskList, Task, FamilyEvent
    for model in (ShoppingList, ShoppingItem, TaskList, Task, FamilyEvent):
        post_delete.connect(deleted, sender=model, weak=False, dispatch_uid=f'sync-delete-{model.__name__}')
    m2m_changed.connect(participants_changed, sender=FamilyEvent.participants.through, weak=False, dispatch_uid='sync-event-participants')


def deleted(sender, instance, using, **kwargs):
    # Removing a whole family does not leave a journal for that deleted tenant.
    origin = kwargs.get('origin')
    if type(origin).__name__ == 'Family' or getattr(getattr(origin, 'model', None), '__name__', '') == 'Family':
        return
    # Django Collector sends post_delete within its transaction, including cascades.
    with sync_lock(using):
        instance.version += 1
        append_change(instance, 'delete', [], using)


def participants_changed(sender, instance, action, reverse, using, **kwargs):
    if not reverse and action in {'post_add', 'post_remove', 'post_clear'}:
        with sync_lock(using):
            instance.refresh_from_db(fields=['version'])
            instance.save(update_fields=['updated_at'])
            from .sync_models import SyncJournal
            journal = SyncJournal.objects.using(using).filter(entity_type='event', entity_id=instance.pk).latest('cursor')
            journal.changed_fields = sorted(set(journal.changed_fields) | {'participants'})
            journal.save(update_fields=['changed_fields'])
