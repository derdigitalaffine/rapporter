from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .memory import normalize_name
from .models import ShoppingItem, ShoppingList, ShoppingPredictionFeedback, ShoppingPurchaseEvent
from .predictions import (
    MAX_SHOPPING_SUGGESTIONS,
    MIN_SHOPPING_CONFIDENCE,
    MIN_SHOPPING_PURCHASES,
    SHOPPING_RECENCY_DECAY,
    _event_intervals,
    _interval_stats,
    _open_names,
    _suppressed_feedback,
    _zone,
    shopping_predictions as family_shopping_predictions,
    suppress_shopping_prediction,
)
from .shopping_models import ShoppingListStoreProfile


MIN_STORE_PURCHASES = 3


def _target_store(family, list_id):
    if not list_id:
        return None
    target = ShoppingList.objects.filter(id=list_id, family=family, archived=False).first()
    if not target:
        raise ValueError("Einkaufsliste gehört nicht zu dieser Familie.")
    assignment = (
        ShoppingListStoreProfile.objects.select_related("store")
        .filter(shopping_list=target, store__family=family)
        .first()
    )
    return assignment.store if assignment else None


def _store_context(event):
    return getattr(event, "store_context", None)


def _rows_for_store(rows, store):
    if not store:
        return []
    return [
        row
        for row in rows
        if (context := _store_context(row)) is not None
        and context.shopping_store_id == store.id
    ]


def _eligible_stats(rows, family, *, minimum=MIN_SHOPPING_PURCHASES):
    if len(rows) < minimum:
        return None
    stats = _interval_stats(
        _event_intervals(rows, family),
        recency_decay=SHOPPING_RECENCY_DECAY,
    )
    if not stats or stats["interval_count"] < 2 or stats["confidence"] < MIN_SHOPPING_CONFIDENCE:
        return None
    return stats


def _normalized_choice(value):
    return " ".join(str(value or "").split()).casefold()


def _learned_value(events, field):
    """Choose a stable recent value without inventing quantity/unit conversions.

    Repeated values gain evidence, newer observations gain exponentially more
    weight, and ties prefer the most recent exact spelling. This lets values such
    as ``2 l`` or ``500 g`` remain user-controlled and unit-safe.
    """
    rows = list(events)
    if not rows:
        return ""
    scores = defaultdict(float)
    latest = {}
    display = {}
    size = len(rows)
    for index, event in enumerate(rows):
        raw = " ".join(str(getattr(event, field, "") or "").split())
        key = _normalized_choice(raw)
        if not key:
            continue
        scores[key] += SHOPPING_RECENCY_DECAY ** (size - index - 1)
        latest[key] = index
        display[key] = raw
    if not scores:
        return ""
    winner = max(scores, key=lambda key: (scores[key], latest[key]))
    return display[winner]


def _learned_defaults(events, *, store=None):
    rows = list(events)
    return {
        "quantity": _learned_value(rows, "quantity"),
        "category": _learned_value(rows, "category"),
        "aisle": _learned_value(rows, "aisle"),
        "store": store.display_label if store else _learned_value(rows, "store"),
    }


def _prediction_row(key, rows, stats, family, now, *, basis, store=None):
    zone = _zone(family)
    local_now = now.astimezone(zone)
    last = rows[-1].purchased_at.astimezone(zone)
    expected_at = last + timedelta(days=stats["expected_interval_days"])
    window_start = expected_at - timedelta(days=stats["window_half_days"])
    window_end = expected_at + timedelta(days=stats["window_half_days"])
    preparation_start = window_start - timedelta(days=stats["preparation_days"])
    if local_now < preparation_start:
        return None
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
    return {
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
            "basis": basis,
            "recency_weighting": "exponential",
            "shopping_store_id": str(store.id) if store else None,
            "shopping_store_label": store.display_label if store else "",
        },
        "defaults": _learned_defaults(rows, store=store if basis == "shopping_store_purchase_history" else None),
        "score": round(score, 2),
    }


def shopping_predictions(family, now=None, list_id=None, limit=MAX_SHOPPING_SUGGESTIONS):
    """Return family predictions, refined by a canonical shopping place when safe.

    Store-specific evidence is opt-in through a concrete target list. It is used
    only after the same minimum purchase/interval/confidence gates as family-wide
    learning. Thin or legacy-only evidence falls back to the established family
    predictor semantics.
    """
    now = now or timezone.now()
    target_store = _target_store(family, list_id)
    grouped = defaultdict(list)
    events = (
        ShoppingPurchaseEvent.objects.filter(family=family)
        .select_related("shopping_list", "store_context__shopping_store")
        .order_by("normalized_name", "purchased_at")
    )
    for event in events:
        grouped[event.normalized_name].append(event)

    open_names = _open_names(family)
    suppressed = _suppressed_feedback(family, now)
    suggestions = []

    for key, family_rows in grouped.items():
        if len(family_rows) < MIN_SHOPPING_PURCHASES or key in open_names or key in suppressed:
            continue
        family_stats = _eligible_stats(family_rows, family)
        if not family_stats:
            continue

        rows = family_rows
        stats = family_stats
        basis = "family_purchase_history"
        evidence_store = None
        if target_store:
            store_rows = _rows_for_store(family_rows, target_store)
            store_stats = _eligible_stats(store_rows, family, minimum=MIN_STORE_PURCHASES)
            if store_stats:
                rows = store_rows
                stats = store_stats
                basis = "shopping_store_purchase_history"
                evidence_store = target_store

        suggestion = _prediction_row(
            key,
            rows,
            stats,
            family,
            now,
            basis=basis,
            store=evidence_store,
        )
        if suggestion:
            suggestions.append(suggestion)

    suggestions.sort(key=lambda row: (-row["score"], row["name"].casefold()))
    bounded_limit = max(1, min(int(limit or MAX_SHOPPING_SUGGESTIONS), MAX_SHOPPING_SUGGESTIONS))
    return {"generated_at": now, "suggestions": suggestions[:bounded_limit]}


def _suggestion_by_key(family, key, *, list_id=None, now=None):
    normalized = normalize_name(key)
    scoped = shopping_predictions(family, now=now, list_id=list_id)
    suggestion = next((row for row in scoped["suggestions"] if row["key"] == normalized), None)
    if suggestion or not list_id:
        return suggestion
    # A suggestion rendered without list context must remain acceptable even if
    # the selected store's cadence is not due yet. In that case preserve the
    # family-wide due decision but still learn store-specific defaults below.
    fallback = family_shopping_predictions(family, now=now)
    return next((row for row in fallback["suggestions"] if row["key"] == normalized), None)


def _refine_defaults_for_store(family, suggestion, list_id):
    store = _target_store(family, list_id)
    if not store or not suggestion:
        return suggestion
    rows = list(
        ShoppingPurchaseEvent.objects.filter(
            family=family,
            normalized_name=suggestion["key"],
            store_context__shopping_store=store,
            store_context__shopping_store__family=family,
        )
        .select_related("store_context")
        .order_by("purchased_at")
    )
    if _eligible_stats(rows, family, minimum=MIN_STORE_PURCHASES):
        suggestion = {**suggestion, "defaults": _learned_defaults(rows, store=store)}
    return suggestion


@transaction.atomic
def accept_shopping_prediction(family, key, user, list_id=None, now=None):
    normalized = normalize_name(key)
    if not normalized:
        raise ValueError("Ungültiger Prediction-Schlüssel.")
    suggestion = _suggestion_by_key(family, normalized, list_id=list_id, now=now)
    suggestion = _refine_defaults_for_store(family, suggestion, list_id)

    from .shopping_access import visible_shopping_lists

    visible_lists = visible_shopping_lists(
        user,
        ShoppingList.objects.filter(family=family, archived=False),
    )
    existing = None
    for item in ShoppingItem.objects.filter(shopping_list__in=visible_lists, checked=False).select_related("shopping_list"):
        if normalize_name(item.name) == normalized:
            existing = item
            break
    if existing:
        return existing, False
    if not suggestion:
        raise ValueError("Dieser Vorschlag ist nicht mehr aktuell.")
    target = ShoppingList.objects.filter(id=list_id, family=family, archived=False).first() if list_id else None
    if target is None:
        target = ShoppingList.objects.filter(family=family, archived=False).order_by("sort_order", "created_at").first()
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
            item, created = accept_shopping_prediction(
                family,
                suggestion["key"],
                user,
                list_id=list_id,
                now=now,
            )
        except ValueError:
            continue
        if created:
            items.append(item)
    return items


__all__ = [
    "accept_all_shopping_predictions",
    "accept_shopping_prediction",
    "shopping_predictions",
    "suppress_shopping_prediction",
]
