from __future__ import annotations

from datetime import datetime, timedelta


_EXPLANATIONS = {
    "title_match": "Passt zu deiner Eingabe.",
    "due_now": "Passt zu einer aktuell fälligen Aktion.",
    "history_weekday": "Vorgeschlagen, weil du das an diesem Wochentag häufiger erledigst.",
    "history_time": "Vorgeschlagen, weil du das häufig ungefähr um diese Zeit erledigst.",
    "frequent_history": "Vorgeschlagen, weil du diese Aktion regelmäßig erledigst.",
    "recent_completion": "Vorgeschlagen, weil du diese Aktion kürzlich erledigt hast.",
    "assigned_to_me": "Dir zugeordnet.",
    "available": "Verfügbare Aktion deiner Familie.",
}


def _bucket(moment: datetime) -> int:
    return moment.hour // 3


def _context_signal(item: dict, observations: list[datetime], now: datetime) -> tuple[float, str]:
    """Return a bounded context boost and its strongest explainable signal."""
    signals: list[tuple[float, str]] = []
    if item.get("state") in {"due", "overdue"}:
        signals.append((0.12, "due_now"))

    recent = sorted(
        (value for value in observations if value <= now and value >= now - timedelta(days=90)),
        reverse=True,
    )
    if recent:
        same_weekday = sum(value.weekday() == now.weekday() for value in recent)
        same_bucket = sum(_bucket(value) == _bucket(now) for value in recent)
        if same_weekday >= 2:
            signals.append((0.08, "history_weekday"))
        if same_bucket >= 2:
            signals.append((0.06, "history_time"))
        frequency = min(0.05, len(recent) * 0.005)
        if frequency:
            signals.append((frequency, "frequent_history"))
        if recent[0] >= now - timedelta(days=7):
            signals.append((0.03, "recent_completion"))

    if not signals:
        return 0.0, "available"
    score = min(0.24, sum(weight for weight, _ in signals))
    strongest = max(signals, key=lambda signal: signal[0])[1]
    return score, strongest


def rank_capture_suggestions(
    suggestions: list[dict], histories: dict[str, list[datetime]], now: datetime
) -> list[dict]:
    """Re-rank already tenant-scoped candidates without mutating source rows or learning state."""
    ranked = []
    for item in suggestions:
        row = dict(item)
        context_score, context_reason = _context_signal(row, histories.get(row["id"], []), now)
        text_score = float(row.get("capture_match") or 0.0)
        # Typed text remains dominant. Context can only reorder plausible candidates
        # that the canonical capture endpoint already admitted.
        final_score = text_score * 0.8 + context_score * 0.2 if text_score else context_score
        row["capture_rank"] = round(final_score, 3)
        if row.get("capture_reason") != "title_match" and context_reason != "available":
            row["capture_reason"] = context_reason
        row["capture_explanation"] = _EXPLANATIONS.get(
            row.get("capture_reason"), _EXPLANATIONS["available"]
        )
        ranked.append(row)

    ranked.sort(
        key=lambda row: (
            -row["capture_rank"],
            -float(row.get("capture_match") or 0.0),
            row.get("title", "").casefold(),
            row.get("id", ""),
        )
    )
    return ranked
