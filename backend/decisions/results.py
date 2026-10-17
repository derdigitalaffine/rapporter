from .models import Decision


def option_metrics(votes):
    rows = list(votes)
    ranks = [vote.rank for vote in rows if vote.rank is not None]
    scores = [vote.score for vote in rows if vote.score is not None]
    return {
        "votes": len(rows),
        "average_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
    }


def summarize_result(decision, option_rows):
    candidates = []
    if decision.mode == Decision.Mode.RANKING:
        metric = "average_rank"
        for option, payload in option_rows:
            if payload[metric] is not None:
                candidates.append((payload[metric], option))
        if not candidates:
            return {"metric": metric, "winner": None, "leaders": [], "is_tie": False}
        best = min(value for value, _ in candidates)
    elif decision.mode == Decision.Mode.RATING:
        metric = "average_score"
        for option, payload in option_rows:
            if payload[metric] is not None:
                candidates.append((payload[metric], option))
        if not candidates:
            return {"metric": metric, "winner": None, "leaders": [], "is_tie": False}
        best = max(value for value, _ in candidates)
    else:
        metric = "votes"
        candidates = [(payload[metric], option) for option, payload in option_rows]
        best = max((value for value, _ in candidates), default=0)
        if best <= 0:
            return {"metric": metric, "winner": None, "leaders": [], "is_tie": False}

    leaders = [
        {"id": str(option.id), "label": option.label, "value": value}
        for value, option in candidates
        if value == best
    ]
    return {
        "metric": metric,
        "winner": leaders[0] if len(leaders) == 1 else None,
        "leaders": leaders,
        "is_tie": len(leaders) > 1,
    }
