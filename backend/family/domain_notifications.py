from urllib.parse import urlencode

from .models import Membership
from .models_features import NotificationPreference
from .push import send_user_push


EVENT_SPECS = {
    "task.status_changed": {"pref":"task_assigned", "parent":"tasks", "title":{"de":"Aufgabenstatus geändert", "en":"Task status changed"}, "body":{"de":"{item}: {status}", "en":"{item}: {status}"}},
    "task.list.created": {"pref": "tasks", "title": {"de": "Neue Aufgabenliste", "en": "New task list"}, "body": {"de": "{actor} hat „{list}“ angelegt.", "en": "{actor} created “{list}”."}},
    "task.created": {"pref": "tasks", "title": {"de": "Neue Aufgabe", "en": "New task"}, "body": {"de": "{actor} hat „{item}“ zu {list} hinzugefügt.", "en": "{actor} added “{item}” to {list}."}},
    "task.assigned": {"pref": "task_assigned", "parent": "tasks", "title": {"de": "Neue Aufgabe für dich", "en": "New task for you"}, "body": {"de": "Dir wurde „{item}“ zugewiesen.", "en": "“{item}” was assigned to you."}},
    "task.updated": {"pref": "tasks", "title": {"de": "Aufgabe geändert", "en": "Task updated"}, "body": {"de": "{actor} hat „{item}“ geändert.", "en": "{actor} updated “{item}”."}},
    "task.completed": {"pref": "tasks", "title": {"de": "Aufgabe erledigt", "en": "Task completed"}, "body": {"de": "{actor} hat „{item}“ erledigt.", "en": "{actor} completed “{item}”."}},
    "task.reopened": {"pref": "tasks", "title": {"de": "Aufgabe wieder geöffnet", "en": "Task reopened"}, "body": {"de": "{actor} hat „{item}“ wieder geöffnet.", "en": "{actor} reopened “{item}”."}},
    "shopping.list.created": {"pref": "shopping", "title": {"de": "Neue Einkaufsliste", "en": "New shopping list"}, "body": {"de": "{actor} hat „{list}“ angelegt.", "en": "{actor} created “{list}”."}},
    "shopping.item.created": {"pref": "shopping", "title": {"de": "Neuer Einkaufsartikel", "en": "New shopping item"}, "body": {"de": "{actor} hat {item} zu {list} hinzugefügt.", "en": "{actor} added {item} to {list}."}},
    "shopping.item.updated": {"pref": "shopping", "title": {"de": "Einkaufsartikel geändert", "en": "Shopping item updated"}, "body": {"de": "{actor} hat {item} geändert.", "en": "{actor} updated {item}."}},
    "shopping.item.completed": {"pref": "shopping", "title": {"de": "Einkaufsartikel abgehakt", "en": "Shopping item checked"}, "body": {"de": "{actor} hat {item} abgehakt.", "en": "{actor} checked off {item}."}},
    "shopping.item.reopened": {"pref": "shopping", "title": {"de": "Einkaufsartikel wieder geöffnet", "en": "Shopping item reopened"}, "body": {"de": "{actor} hat {item} wieder geöffnet.", "en": "{actor} reopened {item}."}},
    "shopping.items.cleared": {"pref": "shopping", "title": {"de": "Einkauf aufgeräumt", "en": "Shopping list cleaned up"}, "body": {"de": "{actor} hat erledigte Artikel aus {list} aufgeräumt.", "en": "{actor} cleared completed items from {list}."}},
    "calendar.event.created": {"pref": "calendar", "title": {"de": "Neuer Familientermin", "en": "New family event"}, "body": {"de": "{actor} hat „{item}“ eingetragen.", "en": "{actor} added “{item}”."}},
    "calendar.event.updated": {"pref": "calendar", "title": {"de": "Familientermin geändert", "en": "Family event updated"}, "body": {"de": "{actor} hat „{item}“ geändert.", "en": "{actor} updated “{item}”."}},
    "calendar.event.deleted": {"pref": "calendar", "title": {"de": "Familientermin gelöscht", "en": "Family event deleted"}, "body": {"de": "{actor} hat „{item}“ gelöscht.", "en": "{actor} deleted “{item}”."}},
    "routine.completed": {"pref": "routines", "title": {"de": "Routine erledigt", "en": "Routine completed"}, "body": {"de": "{actor} hat „{item}“ erledigt.", "en": "{actor} completed “{item}”."}},
    "family.member.joined": {"pref": "family_updates", "title": {"de": "Neues Familienmitglied", "en": "New family member"}, "body": {"de": "{member} ist der Familie beigetreten.", "en": "{member} joined the family."}},
    "family.member.updated": {"pref": "family_updates", "title": {"de": "Mitgliedschaft geändert", "en": "Membership updated"}, "body": {"de": "{actor} hat die Rolle von {member} auf {role} geändert.", "en": "{actor} changed {member}’s role to {role}."}},
    "family.member.removed": {"pref": "family_updates", "title": {"de": "Familienmitglied entfernt", "en": "Family member removed"}, "body": {"de": "{actor} hat {member} aus der Familie entfernt.", "en": "{actor} removed {member} from the family."}},
    "inbox.created": {"pref": "messages", "title": {"de": "Neue Familien-Mitteilung", "en": "New family message"}, "body": {"de": "{actor}: {item}", "en": "{actor}: {item}"}},
}


class _SafeContext(dict):
    def __missing__(self, key):
        return ""


def _user_ids(values):
    result = set()
    for value in values or []:
        candidate = getattr(value, "id", value)
        if candidate is not None:
            result.add(str(candidate))
    return result


def _display_name(user, family):
    if not user:
        return "fam-uh-le"
    membership = Membership.objects.filter(family=family, user=user).only("display_name").first()
    return (membership.display_name if membership else "") or user.get_short_name() or user.username


def _target_url(event_type, context):
    if event_type.startswith("task."):
        params = {"page": "tasks"}
        if context.get("task_id"):
            params["task"] = str(context["task_id"])
        if context.get("list_id"):
            params["list"] = str(context["list_id"])
    elif event_type.startswith("shopping."):
        params = {"page": "shopping"}
        if context.get("list_id"):
            params["list"] = str(context["list_id"])
        if context.get("item_id"):
            params["item"] = str(context["item_id"])
    elif event_type.startswith("calendar."):
        params = {"page": "calendar"}
        if context.get("event_id"):
            params["event"] = str(context["event_id"])
    elif event_type.startswith("family."):
        params = {"page": "members"}
    elif event_type.startswith("inbox."):
        params = {"page": "inbox"}
        if context.get("inbox_id"):
            params["item"] = str(context["inbox_id"])
    elif event_type.startswith("routine."):
        params = {"page": "routines"}
        if context.get("routine_id"):
            params["routine"] = str(context["routine_id"])
    else:
        params = {}
    return f"/?{urlencode(params)}" if params else "/"


def _preference_enabled(membership, spec, cache):
    pref = cache.get(membership.id)
    if pref is None:
        return True
    if spec.get("parent") and not getattr(pref, spec["parent"], True):
        return False
    return getattr(pref, spec["pref"], True)


def notify_domain_event(
    family,
    event_type,
    *,
    actor=None,
    context=None,
    target_users=None,
    exclude_users=None,
    url=None,
):
    """Resolve family recipients and send a best-effort domain push without affecting the mutation."""
    spec = EVENT_SPECS.get(event_type)
    if not spec:
        return {"sent": 0, "errors": 0, "recipients": 0}
    context = _SafeContext(context or {})
    context.setdefault("actor", _display_name(actor, family))
    locale = "en" if str(getattr(family, "locale", "de")).lower().startswith("en") else "de"
    title = spec["title"][locale].format_map(context)
    body = spec["body"][locale].format_map(context)
    actor_id = str(getattr(actor, "id", "")) if actor else ""
    targets = _user_ids(target_users)
    excluded = _user_ids(exclude_users)
    if actor_id:
        excluded.add(actor_id)

    memberships = list(Membership.objects.filter(family=family).select_related("user"))
    pref_rows = NotificationPreference.objects.filter(membership__in=memberships)
    pref_cache = {row.membership_id: row for row in pref_rows}
    sent = errors = recipients = 0
    for membership in memberships:
        user_id = str(membership.user_id)
        if user_id in excluded or (targets and user_id not in targets):
            continue
        if not _preference_enabled(membership, spec, pref_cache):
            continue
        from .notification_digests import delivery_policy, enqueue_notification
        policy = delivery_policy(pref_cache.get(membership.id), family, event_type)
        if policy == "drop":
            continue
        recipients += 1
        try:
            if policy == "queue":
                enqueue_notification(membership, event_type, context, url=url)
                continue
            result = send_user_push(
                membership.user,
                title,
                body,
                url or _target_url(event_type, context),
                tag=f"fam-uh-le:{event_type}",
            )
            sent += result.get("sent", 0)
            errors += result.get("errors", 0)
        except Exception:
            errors += 1
    return {"sent": sent, "errors": errors, "recipients": recipients}
