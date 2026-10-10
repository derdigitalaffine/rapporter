import hashlib
import hmac
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings

from family.models import ShoppingItem, ShoppingList, Task, TaskList

from .family_modules import care_access, require_module


TASK_TEMPLATES = [
    ("bag", "Tasche und wichtige Dinge vorbereiten", "Klinik-/Geburtstasche vorbereiten", 35),
    ("documents", "Unterlagen und Termine vorbereiten", "Kinderarzt / U-Termine vorbereiten", 37),
    ("home", "Zuhause vorbereiten", "Schlafplatz und Wickelbereich prüfen", 36),
]


def _task_source(pregnancy, key):
    raw = f"pregnancy-preparation:{pregnancy.id}:{key}".encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), raw, hashlib.sha256).hexdigest()[:32]
    return f"familyos-preparation:{digest}"


def pregnancy_template_items(user, pregnancy, *, include_tasks=True, include_shopping=True):
    require_module(pregnancy.family)
    care_access(user, pregnancy.family, "pregnancy")
    created = {"tasks": [], "shopping_items": []}

    if include_tasks:
        task_list, _ = TaskList.objects.get_or_create(family=pregnancy.family, name="Vorbereitung", defaults={"icon": "sparkles"})
        legacy_source = f"pregnancy:{pregnancy.id}"
        for key, title, legacy_title, week in TASK_TEMPLATES:
            due = pregnancy.expected_due_date - timedelta(weeks=max(0, 40 - week))
            due_at = datetime.combine(due, time(hour=9), tzinfo=ZoneInfo(pregnancy.family.timezone))
            source = _task_source(pregnancy, key)
            task = Task.objects.filter(family=pregnancy.family, source=source).first()
            if not task:
                task = Task.objects.filter(family=pregnancy.family, source=legacy_source, title=legacy_title).first()
            if task:
                task.task_list = task_list
                task.title = title
                task.source = source
                task.due_at = due_at
                task.tags = ["preparation"]
                task.save(update_fields=["task_list", "title", "source", "due_at", "tags", "updated_at"])
            else:
                task = Task.objects.create(
                    family=pregnancy.family,
                    task_list=task_list,
                    title=title,
                    source=source,
                    due_at=due_at,
                    created_by=user,
                    tags=["preparation"],
                )
            created["tasks"].append(task.id)

    if include_shopping:
        shopping_list = ShoppingList.objects.filter(family=pregnancy.family, archived=False).order_by("sort_order", "created_at").first()
        if shopping_list:
            for name in ("Windeln", "Feuchttücher / Waschlappen", "Spucktücher"):
                item, _ = ShoppingItem.objects.get_or_create(shopping_list=shopping_list, name=name, defaults={"category": "Sonstiges", "added_by": user})
                created["shopping_items"].append(item.id)

    return created
