from collections import Counter, defaultdict

from .memory import normalize_name
from .shopping_models import ShoppingSession, ShoppingSessionActivity


MIN_INDEPENDENT_STREAMS = 2
MIN_PAIR_OBSERVATIONS = 2


def _legacy_key(item):
    return (getattr(item, "position", 2**31 - 1), normalize_name(item.name), str(item.id))


def _store_id_from_snapshot(session):
    confirmed = (session.snapshot or {}).get("confirmed_store") or {}
    return str(confirmed.get("id") or "")


def learned_order_for_store(store, items):
    """Project deterministic item order from client-local completed checkout paths.

    Server receipt time, ``created_at`` and the collaboration ``sequence`` cursor
    are intentionally ignored. Each (session, client_stream) is an independent
    partial path, so offline replay and multiple people/devices cannot manufacture
    a global timeline.
    """
    items = list(items)
    legacy = sorted(items, key=_legacy_key)
    current_keys = {normalize_name(item.name) for item in items if normalize_name(item.name)}
    if len(current_keys) < 2:
        return _payload(store, legacy, "legacy", 0.0, 0, 0)

    sessions = [
        session
        for session in ShoppingSession.objects.filter(
            family=store.family,
            status=ShoppingSession.Status.COMPLETED,
        ).only("id", "snapshot")
        if _store_id_from_snapshot(session) == str(store.id)
    ]
    if not sessions:
        return _payload(store, legacy, "legacy", 0.0, 0, 0)

    rows = (
        ShoppingSessionActivity.objects.filter(
            session_id__in=[session.id for session in sessions],
            kind=ShoppingSessionActivity.Kind.ITEM_CHECKED,
            client_stream__gt="",
            client_sequence__isnull=False,
        )
        .only("session_id", "client_stream", "client_sequence", "item_name")
        .order_by("session_id", "client_stream", "client_sequence")
    )
    streams = defaultdict(list)
    for row in rows:
        key = normalize_name(row.item_name)
        if key and key in current_keys:
            streams[(row.session_id, row.client_stream)].append((row.client_sequence, key))

    pair_counts = Counter()
    usable_streams = 0
    for path in streams.values():
        ordered = []
        seen = set()
        for _, key in sorted(path):
            if key in seen:
                continue
            seen.add(key)
            ordered.append(key)
        if len(ordered) < 2:
            continue
        usable_streams += 1
        for left, right in zip(ordered, ordered[1:]):
            if left != right:
                pair_counts[(left, right)] += 1

    total = sum(pair_counts.values())
    if usable_streams < MIN_INDEPENDENT_STREAMS or total < MIN_PAIR_OBSERVATIONS:
        return _payload(store, legacy, "legacy", 0.0, usable_streams, total)

    graph = {key: set() for key in current_keys}
    weights = Counter()
    compared = set()
    supported = 0
    for left, right in sorted(pair_counts):
        unordered = tuple(sorted((left, right)))
        if unordered in compared:
            continue
        compared.add(unordered)
        a, b = unordered
        ab = pair_counts[(a, b)]
        ba = pair_counts[(b, a)]
        supported += max(ab, ba)
        if ab == ba:
            continue
        winner, loser, margin = (a, b, ab - ba) if ab > ba else (b, a, ba - ab)
        graph[winner].add(loser)
        weights[(winner, loser)] = margin

    if not any(graph.values()):
        return _payload(store, legacy, "legacy", 0.0, usable_streams, total)

    remaining = set(graph)
    ordered_keys = []
    while remaining:
        indegree = {key: 0 for key in remaining}
        for source in remaining:
            for target in graph[source]:
                if target in remaining:
                    indegree[target] += 1
        zeros = [key for key, degree in indegree.items() if degree == 0]
        if zeros:
            chosen = min(zeros)
        else:
            def cycle_key(key):
                outgoing = sum(weights[(key, other)] for other in graph[key] if other in remaining)
                incoming = sum(weights[(other, key)] for other in remaining if key in graph[other])
                return (-(outgoing - incoming), key)
            chosen = min(remaining, key=cycle_key)
        ordered_keys.append(chosen)
        remaining.remove(chosen)

    rank = {key: index for index, key in enumerate(ordered_keys)}
    learned = sorted(
        items,
        key=lambda item: (rank.get(normalize_name(item.name), len(rank)), normalize_name(item.name), str(item.id)),
    )
    confidence = round(supported / total, 3) if total else 0.0
    return _payload(store, learned, "learned", confidence, usable_streams, total)


def _payload(store, items, source, confidence, streams, observations):
    return {
        "store": str(store.id),
        "source": source,
        "confidence": confidence,
        "evidence": {"streams": streams, "pair_observations": observations},
        "ordered_items": [
            {"id": str(item.id), "name": item.name, "key": normalize_name(item.name)}
            for item in items
        ],
    }
