from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .action_capture_ranking import rank_capture_suggestions
from .predictions import _zone
from .unified_action_models import Action, ActionCompletion


def rank_family_capture_rows(*, family, rows):
    """Rank already family-scoped projection rows from existing completion history only."""
    if not rows:
        return rows

    task_ids = [row["id"].split(":", 1)[1] for row in rows if row.get("id", "").startswith("task:")]
    routine_ids = [row["id"].split(":", 1)[1] for row in rows if row.get("id", "").startswith("routine:")]
    actions = list(
        Action.objects.filter(family=family)
        .filter(Q(legacy_task_id__in=task_ids) | Q(legacy_routine_id__in=routine_ids))
        .only("id", "legacy_task_id", "legacy_routine_id")
    )
    typed_by_action = {
        action.id: f"task:{action.legacy_task_id}" if action.legacy_task_id else f"routine:{action.legacy_routine_id}"
        for action in actions
    }

    now = timezone.now()
    zone = _zone(family)
    local_now = timezone.localtime(now, zone)
    histories = defaultdict(list)
    completions = (
        ActionCompletion.objects.filter(
            action_id__in=typed_by_action,
            undone_at__isnull=True,
            occurred_at__gte=now - timedelta(days=90),
        )
        .order_by("-occurred_at", "-id")
        .values_list("action_id", "occurred_at")
    )
    for action_id, occurred_at in completions:
        key = typed_by_action[action_id]
        if len(histories[key]) < 64:
            histories[key].append(timezone.localtime(occurred_at, zone))

    return rank_capture_suggestions(rows, histories, local_now)
