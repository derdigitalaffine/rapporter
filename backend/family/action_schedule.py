"""Versioned, bounded schedule evaluation using family wall time, never browser time."""
from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from statistics import median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
import re
from dateutil import rrule, tz

from .recurrence_text import normalize_recurrence_text

WEEKDAYS = ['MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU']
MODES = {'static', 'learning', 'adaptive'}
FREQUENCIES = {'daily': rrule.DAILY, 'weekly': rrule.WEEKLY, 'monthly': rrule.MONTHLY, 'yearly': rrule.YEARLY}


def _integer(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _clock(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('Time must use HH:MM.')
    return time.fromisoformat(value)


def _weekdays(values):
    if not isinstance(values, list) or any(v not in WEEKDAYS for v in values) or len(values) != len(set(values)):
        raise ValueError('Invalid weekdays.')
    return values


def _segment(segment):
    if not isinstance(segment, dict) or set(segment) - {'weekdays', 'preferred_time', 'window', 'date', 'kind'}:
        raise ValueError('Invalid time segment.')
    if 'preferred_time' in segment:
        _clock(segment['preferred_time'])
    if 'window' in segment:
        window = segment['window']
        if not isinstance(window, dict) or set(window) != {'start', 'end'} or _clock(window['start']) > _clock(window['end']):
            raise ValueError('Window must start before it ends on the same day.')
        if 'preferred_time' in segment and not window['start'] <= segment['preferred_time'] <= window['end']:
            raise ValueError('Preferred time must be inside the window.')


def normalize_schedule(value, family_timezone, today=None):
    if not isinstance(value, dict):
        raise ValueError('Schedule must be an object.')
    value = deepcopy(value)
    allowed = {'version', 'timezone', 'mode', 'recurrence', 'anchor_date', 'segments', 'excluded_weekdays', 'exceptions', 'adaptation', 'continue_learning'}
    if set(value) - allowed:
        raise ValueError('Unsupported schedule fields.')
    if value.get('version', 'action-schedule-v1') != 'action-schedule-v1':
        raise ValueError('Unsupported schedule version.')
    value['version'] = 'action-schedule-v1'
    value['timezone'] = value.get('timezone', family_timezone)
    try:
        ZoneInfo(value['timezone'])
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise ValueError('Invalid timezone.')
    value['mode'] = value.get('mode', 'static')
    if value['mode'] not in MODES:
        raise ValueError('Invalid scheduling mode.')
    if 'continue_learning' in value and not isinstance(value['continue_learning'], bool):
        raise ValueError('continue_learning must be a boolean.')
    recurrence = value.get('recurrence')
    if recurrence is None:
        if value['mode'] != 'learning':
            raise ValueError('A static/adaptive schedule requires recurrence.')
    else:
        allowed_recurrence = {'frequency', 'date', 'interval', 'weekdays', 'month_days', 'nth_weekdays', 'months', 'times_per_period', 'business_days'}
        if not isinstance(recurrence, dict) or set(recurrence) - allowed_recurrence:
            raise ValueError('Invalid recurrence.')
        frequency = recurrence.get('frequency')
        if frequency not in {'once', 'hourly', 'quarterly', *FREQUENCIES}:
            raise ValueError('Invalid frequency.')
        if frequency == 'once':
            date.fromisoformat(recurrence.get('date', ''))
        else:
            if not _integer(recurrence.get('interval', 1), 1, 1200):
                raise ValueError('Interval must be 1–1200.')
        business_days = recurrence.get('business_days')
        if business_days is not None and not isinstance(business_days, bool):
            raise ValueError('business_days must be a boolean.')
        if business_days:
            if frequency != 'daily':
                raise ValueError('business_days requires daily recurrence.')
            if any(recurrence.get(key) for key in ('weekdays', 'month_days', 'nth_weekdays', 'months', 'times_per_period')):
                raise ValueError('business_days cannot be combined with calendar selectors or period targets.')
        quota = recurrence.get('times_per_period')
        if quota is not None:
            if not _integer(quota, 1, 50):
                raise ValueError('times_per_period must be between 1 and 50.')
            if frequency not in {'daily', 'weekly', 'monthly'} or recurrence.get('interval', 1) != 1:
                raise ValueError('times_per_period requires a daily, weekly or monthly interval of 1.')
            if any(recurrence.get(key) for key in ('weekdays', 'month_days', 'nth_weekdays', 'months', 'business_days')):
                raise ValueError('times_per_period cannot be combined with calendar selectors.')
        if frequency == 'hourly' and any(recurrence.get(key) for key in ('weekdays', 'month_days', 'nth_weekdays', 'months', 'times_per_period', 'business_days')):
            raise ValueError('Hourly recurrence cannot be combined with calendar selectors.')
        if 'weekdays' in recurrence:
            if not _weekdays(recurrence['weekdays']):
                raise ValueError('Choose at least one weekday.')
        for key, maximum in [('month_days', 31), ('months', 12)]:
            if key in recurrence and (not isinstance(recurrence[key], list) or not recurrence[key] or any(not _integer(v, 1, maximum) for v in recurrence[key])):
                raise ValueError('Invalid calendar days/months.')
        if 'nth_weekdays' in recurrence:
            if not isinstance(recurrence['nth_weekdays'], list) or not recurrence['nth_weekdays'] or len(recurrence['nth_weekdays']) > 7:
                raise ValueError('Invalid nth weekdays.')
            for nth in recurrence['nth_weekdays']:
                if not isinstance(nth, dict) or nth.get('weekday') not in WEEKDAYS or nth.get('ordinal') not in [-1, 1, 2, 3, 4, 5] or isinstance(nth.get('ordinal'), bool):
                    raise ValueError('Invalid nth weekday.')
    today = today or datetime.now(ZoneInfo(value['timezone'])).date()
    value.setdefault('anchor_date', today.isoformat())
    date.fromisoformat(value['anchor_date'])
    seen = set()
    segments = value.get('segments', [])
    if not isinstance(segments, list) or len(segments) > 7:
        raise ValueError('At most one segment per weekday.')
    for segment in segments:
        _segment(segment)
        days = _weekdays(segment.get('weekdays', WEEKDAYS))
        if seen.intersection(days):
            raise ValueError('Overlapping weekday segments.')
        seen.update(days)
    excluded = _weekdays(value.get('excluded_weekdays', []))
    if len(excluded) == 7:
        raise ValueError('At least one weekday must remain.')
    exceptions = value.get('exceptions', [])
    if not isinstance(exceptions, list) or len(exceptions) > 128:
        raise ValueError('At most 128 exceptions.')
    exception_dates = set()
    for exception in exceptions:
        _segment(exception)
        day = date.fromisoformat(exception.get('date', ''))
        if day in exception_dates or exception.get('kind') not in {'skip', 'override'}:
            raise ValueError('Invalid or duplicate exception.')
        exception_dates.add(day)
    adaptation = value.get('adaptation', {})
    if not isinstance(adaptation, dict) or set(adaptation) - {'enabled', 'auto_apply', 'flexible_fields'}:
        raise ValueError('Invalid adaptation.')
    if adaptation.get('auto_apply'):
        raise ValueError('Automatic schedule changes are not enabled; accept proposals explicitly.')
    return value


def local_datetime(day, clock, zone):
    value = datetime.combine(day, clock, tzinfo=zone).replace(fold=0)
    # Gap: shift forward by the DST gap. Fold: use the first occurrence explicitly.
    if not tz.datetime_exists(value):
        value = tz.resolve_imaginary(value)
    return value


def _quarter_index(day):
    return day.year * 4 + (day.month - 1) // 3


def _quarter_bounds(index):
    year, quarter = divmod(index, 4)
    start = date(year, quarter * 3 + 1, 1)
    if quarter == 3:
        next_start = date(year + 1, 1, 1)
    else:
        next_start = date(year, (quarter + 1) * 3 + 1, 1)
    return start, next_start - timedelta(days=1)


def _nth_weekday_between(start, end, weekday, ordinal):
    weekday_index = WEEKDAYS.index(weekday)
    if ordinal > 0:
        day = start + timedelta(days=(weekday_index - start.weekday()) % 7 + 7 * (ordinal - 1))
        return day if day <= end else None
    day = end - timedelta(days=(end.weekday() - weekday_index) % 7 + 7 * (abs(ordinal) - 1))
    return day if day >= start else None


def _quarterly_days(schedule, recurrence, after):
    anchor = date.fromisoformat(schedule['anchor_date'])
    anchor_index = _quarter_index(anchor)
    index = max(anchor_index, _quarter_index(after))
    interval = recurrence.get('interval', 1)
    index += (interval - (index - anchor_index) % interval) % interval
    anchor_month_offset = (anchor.month - 1) % 3
    for _ in range(400):
        start, end = _quarter_bounds(index)
        candidates = []
        if recurrence.get('nth_weekdays'):
            candidates = [_nth_weekday_between(start, end, item['weekday'], item['ordinal']) for item in recurrence['nth_weekdays']]
        elif recurrence.get('weekdays'):
            allowed = {WEEKDAYS.index(item) for item in recurrence['weekdays']}
            day = max(start, after)
            while day <= end:
                if day.weekday() in allowed:
                    candidates.append(day)
                day += timedelta(days=1)
        else:
            month = start.month + anchor_month_offset
            target = date(start.year, month, min(anchor.day, monthrange(start.year, month)[1]))
            candidates = [target]
        for day in sorted({item for item in candidates if item is not None}):
            if day >= after:
                yield day
        index += interval


def _advance_business_days(day, amount):
    remaining = amount
    current = day
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _business_days(schedule, recurrence, after):
    current = date.fromisoformat(schedule['anchor_date'])
    while current.weekday() >= 5:
        current += timedelta(days=1)
    interval = recurrence.get('interval', 1)
    while current < after:
        current = _advance_business_days(current, interval)
    for _ in range(400):
        yield current
        current = _advance_business_days(current, interval)


def _days(schedule, after):
    recurrence = schedule.get('recurrence')
    if not recurrence:
        for offset in range(370):
            yield after + timedelta(days=offset)
        return
    if recurrence['frequency'] == 'once':
        day = date.fromisoformat(recurrence['date'])
        if day >= after:
            yield day
        return
    if recurrence['frequency'] == 'quarterly':
        yield from _quarterly_days(schedule, recurrence, after)
        return
    if recurrence.get('business_days'):
        yield from _business_days(schedule, recurrence, after)
        return
    if recurrence['frequency'] == 'hourly' or recurrence.get('times_per_period'):
        return
    kwargs = {}
    if recurrence.get('weekdays'):
        kwargs['byweekday'] = [WEEKDAYS.index(d) for d in recurrence['weekdays']]
    if recurrence.get('nth_weekdays'):
        kwargs['byweekday'] = [rrule.weekday(WEEKDAYS.index(n['weekday']), n['ordinal']) for n in recurrence['nth_weekdays']]
    if recurrence.get('month_days'):
        kwargs['bymonthday'] = recurrence['month_days']
    if recurrence.get('months'):
        kwargs['bymonth'] = recurrence['months']
    rule = rrule.rrule(FREQUENCIES[recurrence['frequency']], dtstart=datetime.combine(date.fromisoformat(schedule['anchor_date']), time()), interval=recurrence.get('interval', 1), **kwargs)
    for stamp in rule.xafter(datetime.combine(after, time()), count=400, inc=True):
        yield stamp.date()


def _typical(minutes):
    # Circular unwrap about the first sample handles 23:55/00:05 correctly.
    pivot = minutes[0]
    unwrapped = [pivot + ((v - pivot + 720) % 1440 - 720) for v in minutes]
    center = median(unwrapped)
    spread = median(abs(v - center) for v in unwrapped)
    return int(center) % 1440, spread


def _quota_bounds(day, frequency):
    if frequency == 'daily':
        return day, day
    if frequency == 'weekly':
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    if frequency == 'monthly':
        start = day.replace(day=1)
        return start, day.replace(day=monthrange(day.year, day.month)[1])
    raise ValueError('Unsupported quota period.')


def _next_period_start(end):
    return end + timedelta(days=1)


def _next_allowed_day(day, end, excluded):
    while day <= end and WEEKDAYS[day.weekday()] in excluded:
        day += timedelta(days=1)
    return day if day <= end else None


def predict(schedule, observations, now, rejected=()):
    zone = ZoneInfo(schedule['timezone'])
    local_now = now.astimezone(zone)
    observations = sorted((v for v in observations if v <= now), reverse=True)[:64]
    locals_ = [v.astimezone(zone) for v in observations]
    recurrence = schedule.get('recurrence') or {}
    sample_count = len(observations)

    if recurrence.get('frequency') == 'hourly':
        interval = recurrence.get('interval', 1)
        expected = locals_[0] + timedelta(hours=interval) if locals_ else local_now
        excluded = set(schedule.get('excluded_weekdays', []))
        while WEEKDAYS[expected.weekday()] in excluded:
            expected = local_datetime(expected.date() + timedelta(days=1), time(expected.hour, expected.minute, expected.second), zone)
        status = 'due' if local_now >= expected else 'scheduled'
        return {
            'version': 'action-prediction-v2', 'status': status, 'expected_at': expected,
            'window_start': expected, 'window_end': expected, 'day_only': False, 'confidence': 1.0,
            'basis': ['manual_recurrence', 'completion_time'], 'sample_count': sample_count,
            'suggested_schedule_change': None,
        }

    quota = recurrence.get('times_per_period')
    if quota:
        period_start, period_end = _quota_bounds(local_now.date(), recurrence['frequency'])
        completed = sum(period_start <= value.date() <= period_end for value in locals_)
        remaining = max(0, quota - completed)
        excluded = set(schedule.get('excluded_weekdays', []))
        period_window_start = local_datetime(period_start, time(), zone)
        period_window_end = local_datetime(period_end, time(23, 59, 59), zone)
        if remaining == 0:
            next_start = _next_period_start(period_end)
            expected = local_datetime(next_start, time(12), zone)
            status = 'scheduled'
        else:
            due_day = _next_allowed_day(local_now.date(), period_end, excluded)
            if due_day is None:
                expected = local_datetime(period_end, time(23, 59, 59), zone)
                status = 'overdue'
            else:
                expected = local_datetime(due_day, time(12), zone)
                status = 'due' if due_day == local_now.date() else 'scheduled'
        return {
            'version': 'action-prediction-v2', 'status': status, 'expected_at': expected,
            'window_start': period_window_start, 'window_end': period_window_end, 'day_only': True,
            'confidence': 1.0, 'basis': ['manual_recurrence', 'completion_count'],
            'sample_count': sample_count, 'suggested_schedule_change': None,
            'target_count': quota, 'completed_count': min(completed, quota), 'remaining_count': remaining,
            'period_start': period_start.isoformat(), 'period_end': period_end.isoformat(),
        }

    day_profiles = {}
    for index, weekday in enumerate(WEEKDAYS):
        samples = [v.hour * 60 + v.minute for v in locals_ if v.weekday() == index]
        if len(samples) >= 3:
            center, spread = _typical(samples)
            day_profiles[weekday] = (center, spread, len(samples))
    suggestion = None
    basis = ['manual_recurrence'] if schedule.get('recurrence') else ['completion_time']
    learning = schedule['mode'] == 'learning'
    expected = start = end = None
    day_only = False
    for day in _days(schedule, local_now.date()):
        weekday = WEEKDAYS[day.weekday()]
        if weekday in schedule.get('excluded_weekdays', []):
            continue
        exception = next((e for e in schedule.get('exceptions', []) if e['date'] == day.isoformat()), None)
        if exception and exception['kind'] == 'skip':
            continue
        segment = exception or next((s for s in schedule.get('segments', []) if weekday in s.get('weekdays', WEEKDAYS)), {})
        profile = day_profiles.get(weekday)
        preferred = segment.get('preferred_time')
        # A learned weekday prediction requires evidence, not absence-as-exclusion.
        if learning and not schedule.get('recurrence') and not profile:
            if not locals_:
                break
            gaps = [(a.date() - b.date()).days for a, b in zip(locals_, locals_[1:]) if a.date() != b.date()]
            cadence = max(1, round(median(gaps))) if gaps else 1
            target_day = locals_[0].date() + timedelta(days=cadence)
            if day < max(local_now.date(), target_day):
                continue
        if learning and profile:
            minute = profile[0]
            preferred = f'{minute // 60:02}:{minute % 60:02}'
            basis = ['weekday_history', 'completion_time']
        window = segment.get('window')
        if preferred is None and not window:
            day_only = True
            expected = local_datetime(day, time(12), zone)
            start, end = local_datetime(day, time(), zone), local_datetime(day, time(23, 59, 59), zone)
        else:
            expected = local_datetime(day, _clock(preferred or window['start']), zone)
            start = local_datetime(day, _clock(window['start']), zone) if window else expected
            end = local_datetime(day, _clock(window['end']), zone) if window else expected
        # Completion today advances the recurrence. A time passed today remains due.
        if any(v.date() == day for v in locals_):
            continue
        if schedule['mode'] == 'adaptive' and profile and preferred and profile[2] >= 6 and profile[1] <= 30:
            planned = _clock(preferred).hour * 60 + _clock(preferred).minute
            deviation = abs((profile[0] - planned + 720) % 1440 - 720)
            proposed = f'{profile[0] // 60:02}:{profile[0] % 60:02}'
            key = sha256(json.dumps([weekday, preferred, proposed]).encode()).hexdigest()[:24]
            if deviation >= 60 and key not in rejected:
                suggestion = {'proposal_id': key, 'kind': 'weekday_preferred_time', 'current': {'weekday': weekday, 'preferred_time': preferred}, 'proposed': {'weekday': weekday, 'preferred_time': proposed}, 'sample_count': profile[2], 'confidence': min(.95, profile[2] / 10), 'reason_key': 'stable_schedule_deviation'}
        break
    confidence = min(.95, sample_count / 12) if learning else 1.0
    status = 'learning' if learning and sample_count < 3 else 'scheduled'
    if end and now > end:
        status = 'overdue'
    elif start and now >= start:
        status = 'due'
    return {'version': 'action-prediction-v2', 'status': status, 'expected_at': expected, 'window_start': start, 'window_end': end, 'day_only': day_only, 'confidence': confidence, 'basis': basis, 'sample_count': sample_count, 'suggested_schedule_change': suggestion}


def parse_schedule(text, family_timezone, today=None):
    """Parse deterministic DE/EN recurrence text into the canonical action schedule."""
    value, clock, recurrence_override = normalize_recurrence_text(text)
    result = {'version': 'action-schedule-v1', 'timezone': family_timezone, 'mode': 'static'}
    if clock:
        result['segments'] = [{'preferred_time': clock}]
    if recurrence_override is not None:
        result['recurrence'] = recurrence_override
        return normalize_schedule(result, family_timezone, today)

    names = {'montag': 'MO', 'monday': 'MO', 'dienstag': 'TU', 'tuesday': 'TU', 'mittwoch': 'WE', 'wednesday': 'WE', 'donnerstag': 'TH', 'thursday': 'TH', 'freitag': 'FR', 'friday': 'FR', 'samstag': 'SA', 'saturday': 'SA', 'sonntag': 'SU', 'sunday': 'SU'}
    ordinals = {'ersten': 1, 'zweiten': 2, 'dritten': 3, 'vierten': 4, 'fünften': 5, 'letzten': -1, 'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'last': -1}
    weekend_ordinals = {'erste': 1, 'zweite': 2, 'dritte': 3, 'vierte': 4, 'fünfte': 5, 'letzte': -1, 'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'last': -1}
    months = {'januar': 1, 'january': 1, 'februar': 2, 'february': 2, 'märz': 3, 'maerz': 3, 'march': 3, 'april': 4, 'mai': 5, 'may': 5, 'juni': 6, 'june': 6, 'juli': 7, 'july': 7, 'august': 8, 'september': 9, 'oktober': 10, 'october': 10, 'november': 11, 'dezember': 12, 'december': 12}
    period_nth_de = re.fullmatch(r'(?:immer |jeden )?(?:am )?(ersten|zweiten|dritten|vierten|fünften|letzten) (\w+) im (monat|quartal)', value)
    period_nth_en = re.fullmatch(r'(?:always on |every )?(first|second|third|fourth|fifth|last) (\w+) (?:of|in) (?:the )?(month|quarter)', value)
    month_nth_de = re.fullmatch(r'(?:immer )?(?:am )?(ersten|zweiten|dritten|vierten|fünften|letzten) (\w+) im (\w+)', value)
    month_nth_en = re.fullmatch(r'(?:always on |every )?(first|second|third|fourth|fifth|last) (\w+) (?:in|of) (\w+)', value)
    weekend_de = re.fullmatch(r'(?:immer )?(?:das )?(erste|zweite|dritte|vierte|fünfte|letzte) wochenende im (monat|quartal)', value)
    weekend_en = re.fullmatch(r'(?:always |every )?(first|second|third|fourth|fifth|last) weekend (?:of|in) (?:the )?(month|quarter)', value)
    quota_de = re.fullmatch(r'(\d+)\s*(?:x|-?\s*mal)\s+pro\s+(tag|woche|monat)', value)
    quota_en = re.fullmatch(r'(\d+)\s+times?\s+per\s+(day|week|month)', value)
    business_de = re.fullmatch(r'alle (\d+) werktage', value)
    business_en = re.fullmatch(r'every (\d+) business days?', value)
    if value in {'täglich', 'daily', 'jeden tag'}:
        result['recurrence'] = {'frequency': 'daily', 'interval': 1}
    elif value in {'werktags', 'weekdays'}:
        result['recurrence'] = {'frequency': 'weekly', 'interval': 1, 'weekdays': ['MO', 'TU', 'WE', 'TH', 'FR']}
    elif value in {'flexibel', 'learning', 'lernend'}:
        result['mode'] = 'learning'
    elif business_de:
        result['recurrence'] = {'frequency': 'daily', 'interval': int(business_de[1]), 'business_days': True}
    elif business_en:
        result['recurrence'] = {'frequency': 'daily', 'interval': int(business_en[1]), 'business_days': True}
    elif quota_de:
        periods = {'tag': 'daily', 'woche': 'weekly', 'monat': 'monthly'}
        result['recurrence'] = {'frequency': periods[quota_de[2]], 'interval': 1, 'times_per_period': int(quota_de[1])}
    elif quota_en:
        periods = {'day': 'daily', 'week': 'weekly', 'month': 'monthly'}
        result['recurrence'] = {'frequency': periods[quota_en[2]], 'interval': 1, 'times_per_period': int(quota_en[1])}
    elif re.fullmatch(r'(?:jeden|immer|every) (\w+)', value) and value.split()[-1] in names:
        result['recurrence'] = {'frequency': 'weekly', 'weekdays': [names[value.split()[-1]]]}
    elif period_nth_de and period_nth_de[2] in names:
        result['recurrence'] = {'frequency': 'monthly' if period_nth_de[3] == 'monat' else 'quarterly', 'interval': 1, 'nth_weekdays': [{'weekday': names[period_nth_de[2]], 'ordinal': ordinals[period_nth_de[1]]}]}
    elif period_nth_en and period_nth_en[2] in names:
        result['recurrence'] = {'frequency': 'monthly' if period_nth_en[3] == 'month' else 'quarterly', 'interval': 1, 'nth_weekdays': [{'weekday': names[period_nth_en[2]], 'ordinal': ordinals[period_nth_en[1]]}]}
    elif weekend_de:
        result['recurrence'] = {'frequency': 'monthly' if weekend_de[2] == 'monat' else 'quarterly', 'interval': 1, 'nth_weekdays': [{'weekday': 'SA', 'ordinal': weekend_ordinals[weekend_de[1]]}]}
    elif weekend_en:
        result['recurrence'] = {'frequency': 'monthly' if weekend_en[2] == 'month' else 'quarterly', 'interval': 1, 'nth_weekdays': [{'weekday': 'SA', 'ordinal': weekend_ordinals[weekend_en[1]]}]}
    elif month_nth_de and month_nth_de[2] in names and month_nth_de[3] in months:
        result['recurrence'] = {'frequency': 'yearly', 'interval': 1, 'months': [months[month_nth_de[3]]], 'nth_weekdays': [{'weekday': names[month_nth_de[2]], 'ordinal': ordinals[month_nth_de[1]]}]}
    elif month_nth_en and month_nth_en[2] in names and month_nth_en[3] in months:
        result['recurrence'] = {'frequency': 'yearly', 'interval': 1, 'months': [months[month_nth_en[3]]], 'nth_weekdays': [{'weekday': names[month_nth_en[2]], 'ordinal': ordinals[month_nth_en[1]]}]}
    else:
        interval = re.fullmatch(r'(?:alle|every) (\d+) (stunden|hours|tage|days|wochen|weeks|monate|months|quartale|quarters|jahre|years)', value)
        nth = re.fullmatch(r'alle (\d+) monate (?:am|an einem) (ersten|zweiten|dritten|vierten|fünften|letzten) (\w+)', value)
        if interval:
            unit = {'stunden': 'hourly', 'hours': 'hourly', 'tage': 'daily', 'days': 'daily', 'wochen': 'weekly', 'weeks': 'weekly', 'monate': 'monthly', 'months': 'monthly', 'quartale': 'quarterly', 'quarters': 'quarterly', 'jahre': 'yearly', 'years': 'yearly'}
            result['recurrence'] = {'frequency': unit[interval[2]], 'interval': int(interval[1])}
        elif nth and nth[3] in names:
            result['recurrence'] = {'frequency': 'monthly', 'interval': int(nth[1]), 'nth_weekdays': [{'weekday': names[nth[3]], 'ordinal': ordinals[nth[2]]}]}
        else:
            raise ValueError('Use a supported repeat phrase or the visual scheduler.')
    return normalize_schedule(result, family_timezone, today)