"""Offline calendar projections consume the existing recurrence/birthday cores."""
from datetime import datetime, time, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.utils import timezone
from .calendar_recurrence import family_zone, project_event
from .birthdays import calendar_projection


def window(family):
    today=timezone.now().astimezone(family_zone(family)).date()
    return today-timedelta(days=90),today+relativedelta(months=12)


def in_window(queryset,family):
    start,end=window(family)
    start_at=datetime.combine(start,time.min,family_zone(family))
    end_at=datetime.combine(end+timedelta(days=1),time.min,family_zone(family))
    return queryset.filter(Q(starts_at__isnull=True) |
        (Q(starts_at__lt=end_at) & (Q(ends_at__gt=start_at)|Q(starts_at__gte=start_at))) |
        Q(source__isnull=True,type='calendar.event',payload__recurrence__isnull=False))


def projection(queryset,view,family,user,serialize,refresh):
    start,end=window(family)
    result={'calendar_birthdays':calendar_projection(family,user,start,end)}
    if refresh:
        rows=[]
        for event in in_window(queryset,family):
            row=serialize(view,event,'event')
            if event.source_id is None and event.type=='calendar.event':
                rows.extend(project_event(event,row,start,end))
            else:rows.append(row)
        result.update(calendar_occurrences=rows,calendar_window={'start':start.isoformat(),'end':end.isoformat()},calendar_key=f'{timezone.now().astimezone(family_zone(family)).date().isoformat()}:{family.timezone}')
    return result
