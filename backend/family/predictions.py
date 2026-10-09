from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from .memory import normalize_name
from .models import (
    Family,
    Routine,
    ShoppingItem,
    ShoppingList,
    ShoppingPredictionFeedback,
    ShoppingPurchaseEvent,
)


MIN_INTERVAL_DAYS = 1.0
MAX_INTERVAL_SAMPLES = 12
MIN_SHOPPING_PURCHASES = 3
MIN_SHOPPING_CONFIDENCE = 0.50
MAX_SHOPPING_SUGGESTIONS = 8


def _zone(family: Family):
    try:
        return ZoneInfo(family.timezone or "Europe/Berlin")
    except Exception:
        return timezone.get_current_timezone()


def _weighted_median(values):
    if not values:
        return None
    ordered = sorted(enumerate(values, start=1), key=lambda row: row[1])
    total = sum(index for index, _ in ordered)
    threshold = total / 2
    running = 0
    for weight, value in ordered:
        running += weight
        if running >= threshold:
            return float(value)
    return float(ordered[-1][1])


def _interval_stats(intervals):
    usable = [float(value) for value in intervals if value >= MIN_INTERVAL_DAYS][-MAX_INTERVAL_SAMPLES:]
    if not usable:
        return None
    expected = _weighted_median(usable)
    deviations = [abs(value - expected) for value in usable]
    mad = float(median(deviations)) if deviations else 0.0
    sample_component = min(1.0, 0.20 + 0.16 * len(usable))
    variability = mad / max(expected, 1.0)
    regularity = max(0.15, 1.0 - min(1.0, variability * 3.0))
    confidence = max(0.15, min(0.95, sample_component * (0.55 + 0.45 * regularity)))
    half_window = max(1.0, min(expected * 0.35, max(expected * 0.10, mad * 1.5)))
    preparation_days = max(1.0, min(7.0, expected * 0.20))
    return {
        "expected_interval_days": round(expected, 1),
        "mad_days": round(mad, 1),
        "confidence": round(confidence, 2),
        "interval_count": len(usable),
        "window_half_days": round(half_window, 1),
        "preparation_days": round(preparation_days, 1),
    }


def _routine_logs(routine: Routine):
    cache = getattr(routine, "_prefetched_objects_cache", {})
    logs = list(cache.get("logs") or routine.logs.all())
    return sorted((row for row in logs if row.done_at), key=lambda row: row.done_at)


def routine_prediction(routine: Routine, now=None):
    """A goal is the deadline; reliable observations can suggest an earlier visit.

    Recent intervals carry more weight. Repeated taps less than one hour apart do
    not distort learned cadence. Missing logs anchor a goal to creation time.
    """
    now = now or timezone.now()
    zone = _zone(routine.family)
    logs = [log for log in _routine_logs(routine) if log.done_at<=now]
    local_times = [row.done_at.astimezone(zone) for row in logs]
    intervals = [(b-a).total_seconds()/86400 for a,b in zip(local_times,local_times[1:])]
    usable = [x for x in intervals if x>=1/24][-MAX_INTERVAL_SAMPLES:]
    # Preserve the shopping estimator; routines also support multiple runs a day.
    stats = _interval_stats([max(1, x) for x in usable]) if usable else None
    learned = _weighted_median(usable) if usable else None
    if learned and stats:
        variability = median([abs(x-learned) for x in usable])/learned
        stats["confidence"] = round(min(.95, (.20+.16*min(5,len(usable)))*(.55+.45*max(.15,1-min(1,variability*3)))),2)
    goal = routine.target_period_days/routine.target_count if routine.target_count else None
    confidence = stats["confidence"] if stats else 0.0
    expected = goal
    if learned is not None:
        expected = learned if goal is None else min(goal, goal*(1-confidence*.5)+learned*confidence*.5)
    base = {"target_interval_days": round(goal,3) if goal else None, "learned_interval_days": round(learned,3) if learned else None, "confidence": confidence, "sample_count": len(logs), "interval_count": len(usable), "basis": "goal_and_history" if goal and learned else "goal" if goal else "history" if learned else "learning"}
    if expected is None:
        return {**base, "status": "not_enough_data", "expected_interval_days": None, "expected_at": None, "window_start": None, "window_end": None, "preparation_start": None, "days_until_expected": None}
    anchor = local_times[-1] if local_times else routine.created_at.astimezone(zone)
    expected_at = anchor+timedelta(days=expected)
    half_window = min(expected*.1, 1) if goal else stats["window_half_days"]
    window_start = expected_at-timedelta(days=half_window)
    window_end = expected_at+timedelta(days=half_window)
    # A wish is actionable even before learning. Never postpone its deadline.
    if goal:
        window_end = min(window_end,anchor+timedelta(days=goal))
    local_now = now.astimezone(zone)
    if goal is None and (confidence<.55 or len(usable)<2):
        status = "learning"
    elif local_now>window_end:
        status = "overdue"
    elif local_now>=window_start:
        status = "due"
    else:
        status = "upcoming"
    return {**base, "status": status, "expected_interval_days": round(expected,3), "expected_at": expected_at, "window_start": window_start, "window_end": window_end, "preparation_start": window_start-timedelta(days=min(1,expected*.1)), "days_until_expected": round((expected_at-local_now).total_seconds()/86400)}


def _event_intervals(events, family):
    zone = _zone(family)
    dates = [row.purchased_at.astimezone(zone).date() for row in events if row.purchased_at]
    intervals = []
    for previous, current in zip(dates, dates[1:]):
        gap = (current - previous).days
        if gap >= MIN_INTERVAL_DAYS:
            intervals.append(float(gap))
    return intervals


def _learned_defaults(events):
    result = {"quantity": "", "category": "", "aisle": "", "store": ""}
    for event in reversed(events):
        for key in result:
            if not result[key] and getattr(event, key, ""):
                result[key] = getattr(event, key)
        if all(result.values()):
            break
    return result


def _suppressed_feedback(family, now):
    return {
        row.normalized_name: row
        for row in ShoppingPredictionFeedback.objects.filter(family=family, suppress_until__gt=now)
    }


def _open_names(family):
    names = ShoppingItem.objects.filter(
        shopping_list__family=family,
        shopping_list__archived=False,
        checked=False,
    ).values_list("name", flat=True)
    return {normalize_name(name) for name in names if normalize_name(name)}


def shopping_predictions(family: Family, now=None, list_id=None, limit=MAX_SHOPPING_SUGGESTIONS):
    now = now or timezone.now()
    if list_id and not ShoppingList.objects.filter(id=list_id, family=family, archived=False).exists():
        raise ValueError("Einkaufsliste gehört nicht zu dieser Familie.")

    grouped = defaultdict(list)
    events = ShoppingPurchaseEvent.objects.filter(family=family).select_related("shopping_list").order_by("normalized_name", "purchased_at")
    for event in events:
        grouped[event.normalized_name].append(event)

    open_names = _open_names(family)
    suppressed = _suppressed_feedback(family, now)
    zone = _zone(family)
    local_now = now.astimezone(zone)
    suggestions = []

    for key, rows in grouped.items():
        if len(rows) < MIN_SHOPPING_PURCHASES or key in open_names or key in suppressed:
            continue
        stats = _interval_stats(_event_intervals(rows, family))
        if not stats or stats["interval_count"] < 2 or stats["confidence"] < MIN_SHOPPING_CONFIDENCE:
            continue
        last = rows[-1].purchased_at.astimezone(zone)
        expected_at = last + timedelta(days=stats["expected_interval_days"])
        window_start = expected_at - timedelta(days=stats["window_half_days"])
        window_end = expected_at + timedelta(days=stats["window_half_days"])
        preparation_start = window_start - timedelta(days=stats["preparation_days"])
        if local_now < preparation_start:
            continue
        if local_now > window_end:
            state = "overdue"
        elif local_now >= window_start:
            state = "due"
        else:
            state = "upcoming"
        days_until = round((expected_at - local_now).total_seconds() / 86400)
        overdue_days = max(0.0, (local_now - window_end).total_seconds() / 86400)
        proximity = max(0.0, 14.0 - max(0.0, days_until))
        score = stats["confidence"] * 60 + min(30.0, overdue_days * 4) + min(20.0, proximity)
        suggestions.append({
            "key": key,
            "name": rows[-1].display_name,
            "prediction": {
                "status": state,
                "expected_at": expected_at,
                "window_start": window_start,
                "window_end": window_end,
                "expected_interval_days": stats["expected_interval_days"],
                "confidence": stats["confidence"],
                "purchase_count": len(rows),
                "interval_count": stats["interval_count"],
                "days_until_expected": days_until,
                "reason": "usually_every_n_days",
                "last_purchased_at": rows[-1].purchased_at,
                "days_since_purchase": max(0, (local_now.date() - last.date()).days),
            },
            "defaults": _learned_defaults(rows),
            "score": round(score, 2),
        })

    suggestions.sort(key=lambda row: (-row["score"], row["name"].casefold()))
    return {
        "generated_at": now,
        "suggestions": suggestions[: max(1, min(int(limit or MAX_SHOPPING_SUGGESTIONS), 50))],
    }


def _target_list(family, list_id=None):
    if list_id:
        target = ShoppingList.objects.filter(id=list_id, family=family, archived=False).first()
        if not target:
            raise ValueError("Einkaufsliste gehört nicht zu dieser Familie.")
        return target
    return ShoppingList.objects.filter(family=family, archived=False).order_by("sort_order", "created_at").first()


def _suggestion_by_key(family, key, now=None):
    normalized = normalize_name(key)
    result = shopping_predictions(family, now=now, limit=50)
    return next((row for row in result["suggestions"] if row["key"] == normalized), None)


@transaction.atomic
def accept_shopping_prediction(family, key, user, list_id=None, now=None):
    normalized = normalize_name(key)
    if not normalized:
        raise ValueError("Ungültiger Prediction-Schlüssel.")
    suggestion = _suggestion_by_key(family, normalized, now=now)
    existing = None
    for item in ShoppingItem.objects.filter(shopping_list__family=family, shopping_list__archived=False, checked=False).select_related("shopping_list"):
        if normalize_name(item.name) == normalized:
            existing = item
            break
    if existing:
        return existing, False
    if not suggestion:
        raise ValueError("Dieser Vorschlag ist nicht mehr aktuell.")
    target = _target_list(family, list_id)
    if target is None:
        target = ShoppingList.objects.create(family=family, name="Einkauf", icon="cart-shopping")
    defaults = suggestion["defaults"]
    item = ShoppingItem.objects.create(
        shopping_list=target,
        name=suggestion["name"],
        quantity=defaults.get("quantity") or "",
        category=defaults.get("category") or "",
        aisle=defaults.get("aisle") or "",
        added_by=user,
    )
    ShoppingPredictionFeedback.objects.update_or_create(
        family=family,
        normalized_name=normalized,
        defaults={"action": ShoppingPredictionFeedback.Action.ACCEPTED, "suppress_until": None},
    )
    return item, True


@transaction.atomic
def accept_all_shopping_predictions(family, user, list_id=None, now=None):
    suggestions = list(shopping_predictions(family, now=now, list_id=list_id)["suggestions"])
    items = []
    for suggestion in suggestions:
        try:
            item, created = accept_shopping_prediction(family, suggestion["key"], user, list_id=list_id, now=now)
        except ValueError:
            continue
        if created:
            items.append(item)
    return items


def suppress_shopping_prediction(family, key, *, action="snoozed", days=7, now=None):
    now = now or timezone.now()
    normalized = normalize_name(key)
    if not normalized:
        raise ValueError("Ungültiger Prediction-Schlüssel.")
    feedback, _ = ShoppingPredictionFeedback.objects.get_or_create(family=family, normalized_name=normalized)
    if action == ShoppingPredictionFeedback.Action.DISMISSED:
        feedback.dismiss_count += 1
        suppression_days = min(90, 14 * max(1, feedback.dismiss_count))
        feedback.action = ShoppingPredictionFeedback.Action.DISMISSED
    else:
        suppression_days = max(1, min(int(days or 7), 90))
        feedback.action = ShoppingPredictionFeedback.Action.SNOOZED
    feedback.suppress_until = now + timedelta(days=suppression_days)
    feedback.save(update_fields=["action", "suppress_until", "dismiss_count", "updated_at"])
    return feedback
