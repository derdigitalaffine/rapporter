"""Policy-aware prediction; calendars contribute only busy time intervals."""
from copy import deepcopy
from datetime import timedelta
from .action_schedule import predict


def prediction_for(row, observations, now, policy=None, busy_intervals=()):
    schedule = deepcopy(row.schedule)
    if policy and not policy.adaptive_enabled and schedule['mode'] == 'adaptive':
        schedule['mode'] = 'static'
    horizon = now - timedelta(days=policy.learning_history_days if policy else 365)
    observations = [v for v in observations if horizon <= v <= (row.learning_cutoff_at or now)]
    result = predict(schedule, observations, now, row.rejected_proposals)
    expected = result.get('expected_at')
    start, end = result.get('window_start'), result.get('window_end')
    if expected and start and end and start != end and not result['day_only'] and schedule['mode'] != 'static':
        candidate = expected
        duration = timedelta(minutes=row.estimate_minutes or 15)
        for busy_start, busy_end in sorted(busy_intervals):
            if busy_start is not None and busy_end is not None and busy_start < candidate + duration and busy_end > candidate:
                candidate = busy_end
        if candidate != expected and candidate + duration <= end:
            result['expected_at'] = candidate
            result['basis'] = [*result['basis'], 'calendar_busy_free']
            result['calendar_adjustment'] = {'from': expected, 'to': candidate, 'reason_key': 'calendar_busy_free'}
        elif candidate + duration > end:
            result['calendar_conflict'] = True
    return result
