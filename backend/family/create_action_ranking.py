from collections import defaultdict

from .create_action_models import CreateActionPreference, CreateActionStat
from .models import Family, Membership


CREATE_RANKING_VERSION = 1
COLD_START_THRESHOLD = 5


def _bounded_counts(target, source, *, max_keys=24):
    for key, value in (source or {}).items():
        if not isinstance(key, str) or not isinstance(value, int) or value < 0:
            continue
        if key not in target and len(target) >= max_keys:
            continue
        target[key] += value


def preference_payload(membership):
    setting, _ = CreateActionPreference.objects.get_or_create(membership=membership)
    return {
        "smart_ranking_enabled": setting.smart_ranking_enabled,
        "context_ranking_enabled": setting.context_ranking_enabled,
        "time_patterns_enabled": setting.time_patterns_enabled,
        "direct_mode": setting.direct_mode,
        "direct_action_id": setting.direct_action_id,
        "max_quick_actions": setting.max_quick_actions,
        "pinned_action_ids": list(setting.pinned_action_ids or []),
        "hidden_action_ids": list(setting.hidden_action_ids or []),
        "manual_order": list(setting.manual_order or []),
        "learning_scope": setting.learning_scope,
    }


def stats_payload(membership, *, learning_scope="family"):
    memberships = [membership]
    if learning_scope == CreateActionPreference.LearningScope.GLOBAL:
        memberships = list(
            Membership.objects.filter(
                user=membership.user,
                family__status=Family.Status.ACTIVE,
            ).only("id")
        )
    rows = CreateActionStat.objects.filter(membership__in=memberships).order_by("action_id", "id")
    merged = {}
    for row in rows:
        item = merged.setdefault(
            row.action_id,
            {
                "action_id": row.action_id,
                "use_count": 0,
                "last_used_at": None,
                "context_stats": defaultdict(int),
                "time_bucket_stats": defaultdict(int),
            },
        )
        item["use_count"] += row.use_count
        if row.last_used_at and (item["last_used_at"] is None or row.last_used_at > item["last_used_at"]):
            item["last_used_at"] = row.last_used_at
        _bounded_counts(item["context_stats"], row.context_stats)
        _bounded_counts(item["time_bucket_stats"], row.time_bucket_stats)
    result = []
    for action_id in sorted(merged):
        item = merged[action_id]
        result.append(
            {
                "action_id": item["action_id"],
                "use_count": item["use_count"],
                "last_used_at": item["last_used_at"].isoformat() if item["last_used_at"] else None,
                "context_stats": dict(item["context_stats"]),
                "time_bucket_stats": dict(item["time_bucket_stats"]),
            }
        )
    return result


def ranking_payload(membership):
    preferences = preference_payload(membership)
    stats = stats_payload(membership, learning_scope=preferences["learning_scope"])
    return {
        "ranking_version": CREATE_RANKING_VERSION,
        "cold_start_threshold": COLD_START_THRESHOLD,
        "preferences": preferences,
        "stats": stats,
    }
