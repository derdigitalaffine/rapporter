from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

from .todo_models import TodoActionPreference, TodoPreference


FOCUS_RANKING_VERSION = "todo-focus-v1"
MAX_FOCUS_ITEMS = 5


def _as_datetime(value):
    if not value or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _iso_stamp(value):
    value = _as_datetime(value)
    if not value:
        return float("inf")
    try:
        return value.timestamp()
    except (ValueError, OverflowError):
        return float("inf")


def _explanation_reasons(row, *, pinned=False):
    reasons = []
    if pinned:
        reasons.append("pinned")
    state = row.get("state")
    if state == "overdue":
        reasons.append("overdue")
    elif state == "due":
        reasons.append("routine_due" if row.get("kind") == "routine" else "due_today")
    ranking_reasons = set((row.get("ranking") or {}).get("reasons") or [])
    if "assigned_to_me" in ranking_reasons:
        reasons.append("assigned_to_me")
    if row.get("priority") == "high" or "high_priority" in ranking_reasons:
        reasons.append("high_priority")
    if state == "active":
        reasons.append("workflow_active")
    elif state == "waiting":
        reasons.append("workflow_waiting")
    return reasons or ["normal"]


def _chronological_key(row):
    when = row.get("due_at") or row.get("next_due_at")
    state_weight = {
        "overdue": 0,
        "due": 1,
        "active": 2,
        "waiting": 3,
        "open": 4,
        "done_today": 8,
        "done": 9,
        "paused": 9,
    }.get(row.get("state"), 5)
    return (state_weight, _iso_stamp(when), row.get("kind", ""), row.get("id", ""))


def preference_payload(membership):
    setting = TodoPreference.objects.filter(membership=membership).first()
    item_rows = list(TodoActionPreference.objects.filter(membership=membership))
    return {
        "smart_ranking_enabled": setting.smart_ranking_enabled if setting else True,
        "today_sort": setting.today_sort if setting else TodoPreference.TodaySort.SMART,
        "pinned_action_ids": sorted(row.action_id for row in item_rows if row.pinned),
        "hidden_focus_action_ids": sorted(row.action_id for row in item_rows if row.hidden_from_focus),
    }


def _routine_done_today(row, *, membership, now):
    last_done = _as_datetime((row.get("repeat") or {}).get("last_done_at"))
    if not last_done:
        return False
    try:
        zone = ZoneInfo(membership.family.timezone or "UTC")
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return last_done.astimezone(zone).date() == now.astimezone(zone).date()


def apply_todo_preferences(rows, *, membership, now=None):
    """Decorate canonical actions and derive a small explainable focus list.

    This function is presentation-only: it never mutates Task, Routine or RoutineLog.
    Only explicit preference endpoints write TodoPreference/TodoActionPreference rows.
    """
    now = now or timezone.now()
    payload = preference_payload(membership)
    pinned = set(payload["pinned_action_ids"])
    hidden = set(payload["hidden_focus_action_ids"])
    decorated = []
    for row in rows:
        item = dict(row)
        item["smart"] = {
            "pinned": item["id"] in pinned,
            "hidden_from_focus": item["id"] in hidden,
            "reasons": _explanation_reasons(item, pinned=item["id"] in pinned),
            "version": FOCUS_RANKING_VERSION,
        }
        decorated.append(item)

    if not payload["smart_ranking_enabled"] or payload["today_sort"] == TodoPreference.TodaySort.CHRONOLOGICAL:
        decorated.sort(key=_chronological_key)

    if not payload["smart_ranking_enabled"]:
        return decorated, [], payload

    original_position = {row["id"]: index for index, row in enumerate(decorated)}
    candidates = []
    for row in decorated:
        if row["id"] in hidden or row.get("state") in {"done", "done_today", "paused"}:
            continue
        if row.get("kind") == "routine":
            if _routine_done_today(row, membership=membership, now=now):
                continue
            snoozed_until = _as_datetime((row.get("repeat") or {}).get("snoozed_until"))
            if snoozed_until and snoozed_until > now:
                continue
        candidates.append(row)

    # Manual pin is the only preference that outranks the canonical deterministic
    # action projection. Otherwise keep the existing #215 order exactly.
    candidates.sort(key=lambda row: (0 if row["id"] in pinned else 1, original_position[row["id"]]))
    return decorated, candidates[:MAX_FOCUS_ITEMS], payload
