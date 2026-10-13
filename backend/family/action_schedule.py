"""Versioned, bounded schedule evaluation using family wall time, never browser time."""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from statistics import median
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
import re
from dateutil import rrule, tz

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
        if not isinstance(recurrence, dict) or set(recurrence) - {'frequency', 'date', 'interval', 'weekdays', 'month_days', 'nth_weekdays', 'months'}:
            raise ValueError('Invalid recurrence.')
        frequency = recurrence.get('frequency')
        if frequency not in {'once', *FREQUENCIES}:
            raise ValueError('Invalid frequency.')
        if frequency == 'once':
            date.fromisoformat(recurrence.get('date', ''))
        else:
            if not _integer(recurrence.get('interval', 1), 1, 1200):
                raise ValueError('Interval must be 1–1200.')
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


def predict(schedule, observations, now, rejected=()):
    zone = ZoneInfo(schedule['timezone'])
    local_now = now.astimezone(zone)
    observations = sorted((v for v in observations if v <= now), reverse=True)[:64]
    locals_ = [v.astimezone(zone) for v in observations]
    day_profiles = {}
    for index, weekday in enumerate(WEEKDAYS):
        samples = [v.hour * 60 + v.minute for v in locals_ if v.weekday() == index]
        if len(samples) >= 3:
            center, spread = _typical(samples)
            day_profiles[weekday] = (center, spread, len(samples))
    suggestion = None
    basis = ['manual_recurrence'] if schedule.get('recurrence') else ['completion_time']
    learning = schedule['mode'] == 'learning'
    sample_count = len(observations)
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
    """Small explicit DE/EN grammar. Unsupported input requires visual editing."""
    value = text.strip().casefold()
    value = re.sub(r'\s+', ' ', value)
    result = {'version': 'action-schedule-v1', 'timezone': family_timezone, 'mode': 'static'}
    clock = re.search(r'(?:um |at )?(\d{1,2}:\d{2})(?: uhr)?$', value)
    if clock:
        result['segments'] = [{'preferred_time': clock[1].zfill(5)}]
        value = value[:clock.start()].strip()
    names = {'montag': 'MO', 'monday': 'MO', 'dienstag': 'TU', 'tuesday': 'TU', 'mittwoch': 'WE', 'wednesday': 'WE', 'donnerstag': 'TH', 'thursday': 'TH', 'freitag': 'FR', 'friday': 'FR', 'samstag': 'SA', 'saturday': 'SA', 'sonntag': 'SU', 'sunday': 'SU'}
    if value in {'täglich', 'daily', 'jeden tag'}:
        result['recurrence'] = {'frequency': 'daily', 'interval': 1}
    elif value in {'werktags', 'weekdays'}:
        result['recurrence'] = {'frequency': 'weekly', 'weekdays': WEEKDAYS[:5]}
    elif value in {'flexibel', 'learning', 'lernend'}:
        result['mode'] = 'learning'
    elif re.fullmatch(r'(?:jeden|immer|every) (\w+)', value) and value.split()[-1] in names:
        result['recurrence'] = {'frequency': 'weekly', 'weekdays': [names[value.split()[-1]]]}
    else:
        interval = re.fullmatch(r'(?:alle|every) (\d+) (tage|days|wochen|weeks|monate|months|jahre|years)', value)
        nth = re.fullmatch(r'alle (\d+) monate (?:am|an einem) (ersten|zweiten|dritten|vierten|letzten) (\w+)', value)
        if interval:
            unit = {'tage': 'daily', 'days': 'daily', 'wochen': 'weekly', 'weeks': 'weekly', 'monate': 'monthly', 'months': 'monthly', 'jahre': 'yearly', 'years': 'yearly'}
            result['recurrence'] = {'frequency': unit[interval[2]], 'interval': int(interval[1])}
        elif nth and nth[3] in names:
            result['recurrence'] = {'frequency': 'monthly', 'interval': int(nth[1]), 'nth_weekdays': [{'weekday': names[nth[3]], 'ordinal': {'ersten': 1, 'zweiten': 2, 'dritten': 3, 'vierten': 4, 'letzten': -1}[nth[2]]}]}
        else:
            raise ValueError('Use a supported repeat phrase or the visual scheduler.')
    return normalize_schedule(result, family_timezone, today)
