import unicodedata

from django.db.models import F
from django.utils import timezone

from .models import EntryMemory, ShoppingItem, Task


def normalize_name(value):
    return unicodedata.normalize("NFKC", value or "").strip().casefold()


def remember_entry(instance, *, bump=False):
    if getattr(instance,"birthday_context",None):
        return None
    if isinstance(instance, Task):
        family = instance.family
        kind = EntryMemory.Kind.TASK
        name = instance.title
        data = {
            "notes": instance.notes,
            "priority": instance.priority,
            "estimate_minutes": instance.estimate_minutes,
            "recurrence": instance.recurrence,
            "tags": instance.tags or [],
        }
    elif isinstance(instance, ShoppingItem):
        family = instance.shopping_list.family
        kind = EntryMemory.Kind.SHOPPING
        name = instance.name
        data = {
            "quantity": instance.quantity,
            "category": instance.category,
            "aisle": instance.aisle,
            "note": instance.note,
            "favorite": instance.favorite,
        }
    else:
        return None
    normalized = normalize_name(name)
    if not normalized:
        return None
    memory, created = EntryMemory.objects.get_or_create(
        family=family,
        kind=kind,
        normalized_name=normalized,
        defaults={"name": name, "data": data, "use_count": 1, "last_used_at": timezone.now()},
    )
    if not created:
        memory.name = name
        memory.data = data
        memory.last_used_at = timezone.now()
        if bump:
            EntryMemory.objects.filter(pk=memory.pk).update(use_count=F("use_count") + 1)
            memory.refresh_from_db(fields=["use_count"])
        memory.save(update_fields=["name", "data", "last_used_at", "updated_at"])
    return memory


def suggestions(family, kind, query="", limit=12):
    needle = normalize_name(query)
    rows = EntryMemory.objects.filter(family=family, kind=kind)
    if needle:
        rows = rows.filter(normalized_name__contains=needle)
    now = timezone.now()
    result = []
    for row in rows.order_by("-last_used_at")[:200]:
        age_days = max(0, (now - row.last_used_at).days)
        score = row.use_count * 20 + max(0, 30 - min(age_days, 30))
        result.append({
            "name": row.name,
            "count": row.use_count,
            "last_used": row.last_used_at,
            "score": score,
            **(row.data or {}),
        })
    return sorted(result, key=lambda item: (-item["score"], item["name"].casefold()))[:limit]
