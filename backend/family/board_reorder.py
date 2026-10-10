from bisect import bisect_left


DEFAULT_POSITION_GAP = 1000


def _stable_anchor_ids(current, ordered):
    """Return a longest subsequence that can keep its existing positions.

    `current` is already in canonical board order. Mapping the requested order
    back to current indices turns the maximum set of rows that need no move into
    a longest increasing subsequence problem.
    """
    current_index = {row.id: index for index, row in enumerate(current)}
    sequence = [current_index[row.id] for row in ordered]
    tails = []
    tail_indices = []
    previous = [-1] * len(sequence)

    for index, value in enumerate(sequence):
        slot = bisect_left(tails, value)
        if slot == len(tails):
            tails.append(value)
            tail_indices.append(index)
        else:
            tails[slot] = value
            tail_indices[slot] = index
        if slot:
            previous[index] = tail_indices[slot - 1]

    if not tail_indices:
        return set()

    anchors = set()
    cursor = tail_indices[-1]
    while cursor >= 0:
        anchors.add(ordered[cursor].id)
        cursor = previous[cursor]
    return anchors


def _full_rebalance(ordered, gap):
    planned = []
    for index, row in enumerate(ordered):
        position = index * gap
        if row.position != position:
            planned.append((row, position))
    return planned


def plan_board_positions(current, ordered, *, gap=DEFAULT_POSITION_GAP):
    """Plan a reorder while preserving as many persisted positions as possible.

    Small moves normally update only the moved rows by using integer gaps between
    stable neighbours. When a gap is exhausted, the function falls back to a
    deterministic full rebalance so ordering never depends on fractional values
    or database-specific numeric behaviour.
    """
    if len(current) != len(ordered) or {row.id for row in current} != {row.id for row in ordered}:
        raise ValueError("current and ordered must contain the same board rows")
    if not ordered:
        return []
    if gap < 2:
        raise ValueError("gap must leave room for future moves")
    if [row.id for row in current] == [row.id for row in ordered]:
        return []

    anchor_ids = _stable_anchor_ids(current, ordered)
    planned = []
    cursor = 0

    while cursor < len(ordered):
        if ordered[cursor].id in anchor_ids:
            cursor += 1
            continue

        start = cursor
        while cursor < len(ordered) and ordered[cursor].id not in anchor_ids:
            cursor += 1
        end = cursor
        segment = ordered[start:end]
        left = ordered[start - 1] if start else None
        right = ordered[end] if end < len(ordered) else None

        if left is not None and right is not None:
            available = right.position - left.position - 1
            if available < len(segment):
                return _full_rebalance(ordered, gap)
            step = (right.position - left.position) // (len(segment) + 1)
            if step < 1:
                return _full_rebalance(ordered, gap)
            positions = [left.position + step * (offset + 1) for offset in range(len(segment))]
        elif left is not None:
            positions = [left.position + gap * (offset + 1) for offset in range(len(segment))]
        elif right is not None:
            first = right.position - gap * len(segment)
            positions = [first + gap * offset for offset in range(len(segment))]
        else:
            return _full_rebalance(ordered, gap)

        for row, position in zip(segment, positions):
            if row.position != position:
                planned.append((row, position))

    return planned
