from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlencode

from django.db.models import F, Prefetch, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from .models import Family, Membership, Routine, RoutineLog, RoutineReminderState, Task
from .predictions import _zone, routine_prediction


RANKING_VERSION = "actions-v1"
MAX_ROUTINE_LOGS = 64
RECENT_DAYS = 30
VALID_SCOPES = {"today", "upcoming", "all", "mine", "tasks", "routines", "completed", "recent"}
VALID_KINDS = {"all", "task", "tasks", "routine", "routines"}


class ActionProjectionError(ValueError):
    pass


def parse_action_id(value: str, *, expected_kind: str | None = None) -> tuple[str, str]:
    """Parse a typed projection ID without ever guessing a backing model."""
    try:
        kind, object_id = str(value).split(":", 1)
    except ValueError as exc:
        raise ActionProjectionError("Ungültige Action-ID.") from exc
    if kind not in {"task", "routine"} or not object_id:
        raise ActionProjectionError("Ungültige Action-ID.")
    if expected_kind and kind != expected_kind:
        raise ActionProjectionError("Action-ID gehört zu einer anderen Domäne.")
    return kind, object_id


def _action(kind: str, action_id: str, method: str, href: str, payload=None):
    data = {"id": action_id, "method": method, "href": href}
    if payload is not None:
        data["payload"] = payload
    return data


def _deep_link(page: str, family_id, **params):
    values = {
        "page": page,
        "family": str(family_id),
        **{key: str(value) for key, value in params.items() if value is not None},
    }
    return "/?" + urlencode(values)


def _local_day(value, zone):
    return value.astimezone(zone).date() if value else None


def _task_state(task: Task, *, today, zone):
    completed_day = _local_day(task.completed_at, zone)
    due_day = _local_day(task.due_at, zone)
    workflow_kind = task.workflow_column.kind if task.workflow_column_id else None
    if task.completed_at:
        return "done_today" if completed_day == today else "done"
    if due_day and due_day < today:
        return "overdue"
    if due_day == today:
        return "due"
    if workflow_kind == "active":
        return "active"
    if workflow_kind == "waiting":
        return "waiting"
    return "open"


def _ranking(kind: str, state: str, *, priority="normal", mine=False):
    reasons = []
    if state == "overdue":
        bucket = 0
        reasons.append("overdue")
    elif state == "due":
        bucket = 1 if kind == "task" else 3
        reasons.append("due_now")
    elif state in {"active", "waiting"}:
        bucket = 2
        reasons.append(f"workflow_{state}")
    elif priority == "high" or mine:
        bucket = 4
        if priority == "high":
            reasons.append("high_priority")
        if mine:
            reasons.append("assigned_to_me")
    elif state == "done_today":
        bucket = 6
        reasons.append("done_today")
    elif state in {"done", "paused"}:
        bucket = 7
        reasons.append(state)
    else:
        bucket = 5
        reasons.append("normal")
    return {"version": RANKING_VERSION, "bucket": bucket, "reasons": reasons}


def _urgency(state: str, priority: str = "normal"):
    if state == "overdue":
        return "critical"
    if state in {"due", "active", "waiting"} or priority == "high":
        return "high"
    if state in {"done", "done_today", "paused"}:
        return "none"
    return "normal"


def _task_item(task: Task, *, user, family: Family, now):
    zone = _zone(family)
    today = now.astimezone(zone).date()
    state = _task_state(task, today=today, zone=zone)
    mine = task.assignee_id == user.id
    ranking = _ranking("task", state, priority=task.priority, mine=mine)
    toggle = _action(
        "task",
        "reopen" if task.completed_at else "complete",
        "POST",
        f"/api/tasks/{task.id}/toggle/",
    )
    edit = _action("task", "edit", "PATCH", f"/api/tasks/{task.id}/")
    actions = [toggle, edit]
    if not task.completed_at:
        actions.append(_action("task", "duel", "GET", _deep_link("games", task.family_id, task=task.id)))
    if task.workflow_column_id:
        actions.append(_action("task", "move", "POST", f"/api/tasks/{task.id}/move/"))
    actions.append(_action("task", "delete", "DELETE", f"/api/tasks/{task.id}/"))
    return {
        "id": f"task:{task.id}",
        "family": str(task.family_id),
        "kind": "task",
        "title": task.title,
        "state": state,
        "due_at": task.due_at,
        "next_due_at": task.due_at if not task.completed_at else None,
        "completed_at": task.completed_at,
        "assignee": ({"id": task.assignee_id, "username": task.assignee.username} if task.assignee_id else None),
        "priority": task.priority,
        "urgency": _urgency(state, task.priority),
        "context": {
            "source": task.source,
            "list": ({"id": str(task.task_list_id), "name": task.task_list.name} if task.task_list_id else None),
            "workflow": (
                {
                    "id": str(task.workflow_column_id),
                    "name": task.workflow_column.name,
                    "kind": task.workflow_column.kind,
                    "terminal": task.workflow_column.is_terminal,
                }
                if task.workflow_column_id
                else None
            ),
        },
        "repeat": {"recurrence": task.recurrence} if task.recurrence else None,
        "tags": task.tags,
        "primary_action": toggle,
        "allowed_actions": actions,
        "deep_link": _deep_link("tasks", task.family_id, task=task.id),
        "ranking": ranking,
        "_sort_at": task.due_at,
        "_mine": mine,
    }


def _routine_item(routine: Routine, *, user, family: Family, now):
    zone = _zone(family)
    today = now.astimezone(zone).date()
    logs = list(routine.logs.all())
    last_done_at = max((log.done_at for log in logs if log.done_at), default=None)
    done_today = any(_local_day(log.done_at, zone) == today for log in logs if log.done_at)
    prediction = routine_prediction(routine, now)
    prediction_status = prediction.get("status")
    if not routine.active:
        state = "paused"
    elif prediction_status == "overdue":
        state = "overdue"
    elif prediction_status == "due":
        state = "due"
    elif done_today:
        state = "done_today"
    else:
        state = "open"

    reminder_state = next(iter(getattr(routine, "_action_reminder_states", [])), None)
    snoozed_until = (
        reminder_state.snoozed_until
        if reminder_state and reminder_state.snoozed_until and reminder_state.snoozed_until > now
        else None
    )
    ranking = _ranking("routine", state)
    if routine.active:
        primary = _action("routine", "record_done", "POST", f"/api/routines/{routine.id}/done/")
        actions = [
            primary,
            _action("routine", "snooze", "POST", f"/api/routines/{routine.id}/snooze/"),
            _action("routine", "edit", "PATCH", f"/api/routines/{routine.id}/"),
        ]
    else:
        primary = _action("routine", "reactivate", "PATCH", f"/api/routines/{routine.id}/", {"active": True})
        actions = [primary, _action("routine", "edit", "PATCH", f"/api/routines/{routine.id}/")]

    return {
        "id": f"routine:{routine.id}",
        "family": str(routine.family_id),
        "kind": "routine",
        "title": routine.name,
        "state": state,
        "due_at": None,
        "next_due_at": prediction.get("expected_at"),
        "completed_at": None,
        "assignee": None,
        "priority": "normal",
        "urgency": _urgency(state),
        "context": {"source": "routine", "list": None, "workflow": None},
        "repeat": {
            "target_count": routine.target_count,
            "target_period_days": routine.target_period_days,
            "reminder_enabled": routine.reminder_enabled,
            "snoozed_until": snoozed_until,
            "last_done_at": last_done_at,
            "prediction": {
                "status": prediction_status,
                "expected_at": prediction.get("expected_at"),
                "window_start": prediction.get("window_start"),
                "window_end": prediction.get("window_end"),
                "basis": prediction.get("basis"),
                "confidence": prediction.get("confidence"),
                "sample_count": prediction.get("sample_count"),
            },
        },
        "tags": [],
        "primary_action": primary,
        "allowed_actions": actions,
        "deep_link": _deep_link("routines", routine.family_id, routine=routine.id),
        "ranking": ranking,
        "_sort_at": prediction.get("expected_at"),
        "_mine": False,
    }


def _normalise_filters(scope: str, kind: str):
    scope = (scope or "today").strip().lower()
    kind = (kind or "all").strip().lower()
    if scope not in VALID_SCOPES:
        raise ActionProjectionError("Unbekannter Action-Scope.")
    if kind not in VALID_KINDS:
        raise ActionProjectionError("Unbekannter Action-Typ.")
    if scope in {"tasks", "routines"}:
        alias_kind = scope
        if kind not in {"all", alias_kind, alias_kind[:-1]}:
            raise ActionProjectionError("Scope und Typ widersprechen sich.")
        kind = alias_kind
        scope = "all"
    if kind == "task":
        kind = "tasks"
    elif kind == "routine":
        kind = "routines"
    return scope, kind


def _task_queryset(*, family, user, scope, list_id=None, workflow_id=None, today_start, tomorrow_start, recent_start):
    rows = Task.objects.filter(family=family).exclude(hidden_from_user=user).select_related(
        "task_list", "assignee", "workflow_column"
    )
    if list_id:
        rows = rows.filter(task_list_id=list_id)
    if workflow_id:
        rows = rows.filter(workflow_column_id=workflow_id)
    if scope == "mine":
        return rows.filter(assignee=user, completed_at__isnull=True)
    if scope == "today":
        return rows.filter(
            Q(completed_at__gte=today_start, completed_at__lt=tomorrow_start)
            | Q(completed_at__isnull=True, due_at__lt=tomorrow_start)
            | Q(completed_at__isnull=True, workflow_column__kind__in=["active", "waiting"])
            | Q(unified_action__schedule__recurrence__frequency__in=["daily", "weekly", "monthly", "quarterly", "yearly"])
        )
    if scope == "upcoming":
        return rows.filter(completed_at__isnull=True, due_at__gte=tomorrow_start)
    if scope in {"completed", "recent"}:
        return rows.filter(completed_at__gte=recent_start)
    return rows.filter(Q(completed_at__isnull=True) | Q(completed_at__gte=today_start) | Q(unified_action__schedule__recurrence__frequency__in=["daily", "weekly", "monthly", "quarterly", "yearly"]))


def _routine_queryset(*, family, user, scope, now, recent_start):
    rows = Routine.objects.filter(family=family).select_related("family")
    if scope in {"today", "upcoming"}:
        rows = rows.filter(active=True)
    elif scope in {"completed", "recent"}:
        rows = rows.filter(logs__done_at__gte=recent_start).distinct()

    # A raw slice cannot be used for a reverse-FK Prefetch on Django 6.1 because
    # the relation manager still has to add its parent filter afterwards. Rank
    # logs per routine in SQL instead: one query, bounded history, no N+1.
    limited_logs = (
        RoutineLog.objects.filter(done_at__lte=now)
        .annotate(
            _action_row=Window(
                expression=RowNumber(),
                partition_by=[F("routine_id")],
                order_by=[F("done_at").desc(), F("id").desc()],
            )
        )
        .filter(_action_row__lte=MAX_ROUTINE_LOGS)
        .select_related("done_by")
        .order_by("routine_id", "-done_at", "-id")
    )
    reminder_states = RoutineReminderState.objects.filter(membership__user=user)
    return rows.prefetch_related(
        Prefetch("logs", queryset=limited_logs),
        Prefetch("reminder_states", queryset=reminder_states, to_attr="_action_reminder_states"),
    )


def _matches_scope(item, *, scope, today, zone, recent_start):
    if scope == "today":
        prediction = item.get("prediction_v2")
        if prediction and prediction.get("expected_at") and _local_day(prediction["expected_at"], zone) == today:
            return True
        return item["state"] in {"overdue", "due", "active", "waiting", "done_today"}
    if scope == "upcoming":
        next_at = item["next_due_at"]
        return item["state"] == "open" and next_at is not None and _local_day(next_at, zone) > today
    if scope == "mine":
        return item["kind"] == "task" and item["_mine"] and item["state"] not in {"done", "done_today"}
    if scope in {"completed", "recent"}:
        if item["kind"] == "task":
            return bool(item["completed_at"] and item["completed_at"] >= recent_start)
        last_done = (item.get("repeat") or {}).get("last_done_at")
        return bool(last_done and last_done >= recent_start)
    return True


def _sort_key(item):
    sort_at = item.get("_sort_at")
    sort_stamp = sort_at.timestamp() if sort_at else float("inf")
    priority_weight = {"high": 0, "normal": 1, "low": 2}.get(item.get("priority"), 1)
    return (
        item["ranking"]["bucket"],
        sort_stamp,
        priority_weight,
        0 if item.get("_mine") else 1,
        item["kind"],
        item["title"].casefold(),
        item["id"],
    )


def _public_item(item):
    return {key: value for key, value in item.items() if not key.startswith("_")}


def project_actions(
    *,
    user,
    family: Family,
    scope: str = "today",
    kind: str = "all",
    list_id=None,
    workflow_id=None,
    task_id=None,
    now=None,
) -> list[dict]:
    """Project canonical tasks/routines into one deterministic, read-only feed."""
    scope, kind = _normalise_filters(scope, kind)
    now = now or timezone.now()
    zone = _zone(family)
    local_now = now.astimezone(zone)
    today = local_now.date()
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    recent_start = now - timedelta(days=RECENT_DAYS)

    if not Membership.objects.filter(user=user, family=family, family__status=Family.Status.ACTIVE).exists():
        raise ActionProjectionError("Familie ist für diesen Benutzer nicht verfügbar.")

    items: list[dict] = []
    include_tasks = kind != "routines"
    include_routines = kind != "tasks" and scope != "mine" and not list_id and not workflow_id and not task_id

    if include_tasks:
        tasks = _task_queryset(
            family=family,
            user=user,
            scope=scope,
            list_id=list_id,
            workflow_id=workflow_id,
            today_start=today_start,
            tomorrow_start=tomorrow_start,
            recent_start=recent_start,
        )
        if task_id:
            tasks = tasks.filter(id=task_id)
        items.extend(_task_item(task, user=user, family=family, now=now) for task in tasks)

    if include_routines:
        routines = _routine_queryset(family=family, user=user, scope=scope, now=now, recent_start=recent_start)
        items.extend(_routine_item(routine, user=user, family=family, now=now) for routine in routines)

    _decorate_unified(items, user=user, family=family, now=now)
    items = [
        item
        for item in items
        if _matches_scope(item, scope=scope, today=today, zone=zone, recent_start=recent_start)
    ]
    items.sort(key=_sort_key)
    return [_public_item(item) for item in items]


def _decorate_unified(items, *, user, family, now):
    """Two bounded queries; keep the versioned v1 command contract as fallback."""
    from .unified_action_models import Action, ActionCompletion
    from .action_prediction import prediction_for
    from .unified_action_models import ActionPolicy, ActionPersonalSetting
    from collections import defaultdict
    from .context_models import ContextLink
    from django.db.models import Exists, OuterRef
    edges = ContextLink.objects.filter(family=family, relation_key='action.context').filter(Q(source_type='task',source_id=OuterRef('legacy_task_id')) | Q(source_type='routine',source_id=OuterRef('legacy_routine_id')))
    rows = list(Action.objects.filter(family=family).exclude(state='archived').annotate(_has_context=Exists(edges)))
    by_id = {}
    for row in rows:
        if row.legacy_task_id:
            by_id[f'task:{row.legacy_task_id}'] = row
        elif row.legacy_routine_id:
            by_id[f'routine:{row.legacy_routine_id}'] = row
    scheduled_ids = [r.id for r in rows if r.schedule]
    policy = ActionPolicy.objects.filter(family=family).first() if scheduled_ids else None
    busy_intervals = []
    if policy and policy.calendar_aware:
        personal = ActionPersonalSetting.objects.filter(membership__family=family,membership__user=user).first()
        if personal and personal.calendar_aware:
            from .models import FamilyEvent
            busy_intervals = list(FamilyEvent.objects.filter(family=family, type="calendar.event", starts_at__gte=now-timedelta(days=1), starts_at__lt=now+timedelta(days=32), ends_at__isnull=False).values_list("starts_at","ends_at")[:1000])
    history = defaultdict(list)
    if scheduled_ids:
        events = (ActionCompletion.objects.filter(action_id__in=scheduled_ids, undone_at__isnull=True, occurred_at__lte=now)
            .annotate(_rank=Window(expression=RowNumber(), partition_by=[F('action_id')], order_by=[F('occurred_at').desc(), F('id').desc()]))
            .filter(_rank__lte=64).values_list('action_id', 'occurred_at'))
        for action_id, occurred_at in events:
            history[action_id].append(occurred_at)
    from .context_models import ContextLink
    from .context_links import default_context_registry, ContextRef
    context_links = list(ContextLink.objects.filter(family=family, relation_key='action.context', source_id__in=[i['id'].split(':',1)[1] for i in items], source_type__in=['task','routine'])) if items and any(r._has_context for r in rows) else []
    resolved = default_context_registry().resolve_many(user, family, [ContextRef(link.context_type, link.context_id) for link in context_links], strict=False) if context_links else {}
    context_by_id = defaultdict(list)
    for link in context_links:
        endpoint = resolved.get(ContextRef(link.context_type, link.context_id))
        if endpoint is not None:
            context_by_id[f'{link.source_type}:{link.source_id}'].append({'type':link.context_type,'id':str(link.context_id),'deep_link':endpoint.deep_link})
    for item in items:
        item['contexts'] = context_by_id[item['id']][:5]
        item['completion_command'] = {'href': '/api/actions/execute/', 'version': 'action-completion-v1'}
        row = by_id.get(item['id'])
        if row is None:
            continue
        item['canonical_action_id'] = str(row.id)
        item['icon'] = row.icon or 'tasks'
        item['accent_token'] = row.accent_token
        if row.schedule:
            prediction = prediction_for(row, history[row.id], now, policy, busy_intervals)
            item['prediction_v2'] = prediction
            item['schedule'] = row.schedule
            # New schedule intent applies only to configured actions. Legacy feed
            # fields and algorithms stay available until the explicit cutover.
            recurring_task = item['kind'] == 'task' and row.schedule.get('recurrence', {}).get('frequency') in {'daily','weekly','monthly','quarterly','yearly'}
            if (item['kind'] == 'routine' or recurring_task) and item['state'] not in {'paused', 'done_today'}:
                if recurring_task:
                    item['primary_action'] = _action('task', 'complete', 'POST', f'/api/tasks/{row.legacy_task_id}/toggle/')
                item['next_due_at'] = prediction['expected_at']
                item['_sort_at'] = prediction['expected_at']
                item['state'] = prediction['status'] if prediction['status'] in {'due', 'overdue'} else 'open'
                item['urgency'] = _urgency(item['state'])
                item['ranking'] = _ranking('routine', item['state'])
