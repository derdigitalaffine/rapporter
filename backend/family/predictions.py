from collections import defaultdict
from datetime import timedelta
from statistics import mean, median, pstdev

from django.utils import timezone

from .memory import normalize_name
from .models import Routine, RoutineLog, ShoppingItem
from .models_features import PredictionFeedback, ShoppingPurchaseEvent

MIN_SAMPLES=3
MIN_CONFIDENCE=.55
DUE_WINDOW_DAYS=2


def _pattern(dates,min_samples=MIN_SAMPLES):
    dates=sorted(dates)
    if len(dates)<min_samples:return None
    intervals=[max(.25,(right-left).total_seconds()/86400) for left,right in zip(dates,dates[1:])]
    typical=float(median(intervals));spread=pstdev(intervals) if len(intervals)>1 else 0;cv=spread/max(mean(intervals),.25)
    confidence=min(.95,.42+.08*min(len(dates)-2,5)+.38*(1-min(cv,1)))
    window=max(1.0,min(7.0,typical*(.12+.35*min(cv,1))))
    return {"interval_days":round(typical,1),"variability_days":round(spread,1),"window_days":round(window,1),"confidence":round(confidence,2),"sample_count":len(dates),"last":dates[-1],"due_at":dates[-1]+timedelta(days=typical)}

def routine_prediction(routine,now=None):
    now=now or timezone.now();dates=list(RoutineLog.objects.filter(routine=routine).order_by("done_at").values_list("done_at",flat=True));pattern=_pattern(dates,min_samples=2)
    if not pattern:return {"status":"not_enough_data","expected_interval_days":None,"expected_at":None,"window_start":None,"window_end":None,"confidence":0,"sample_count":len(dates),"days_until_expected":None}
    expected=pattern["due_at"];window=timedelta(days=pattern["window_days"]);start=expected-window;end=expected+window;days=round((expected-now).total_seconds()/86400)
    if pattern["confidence"]<MIN_CONFIDENCE:status="learning"
    elif now>end:status="overdue"
    elif now>=start:status="due"
    else:status="upcoming"
    return {"status":status,"expected_interval_days":pattern["interval_days"],"expected_at":expected,"window_start":start,"window_end":end,"confidence":pattern["confidence"],"sample_count":pattern["sample_count"],"days_until_expected":days}

def _confidence_label(value):return "high" if value>=.75 else "medium" if value>=.55 else "low"

def _feedback_map(family,membership):return {(row.kind,row.subject_key):row for row in PredictionFeedback.objects.filter(family=family,membership=membership)}

def _suppressed(feedback,now):return bool(feedback and (feedback.dismissed or (feedback.snoozed_until and feedback.snoozed_until>now)))

def predictions_for(family,membership):
    now=timezone.now();feedback=_feedback_map(family,membership);result=[]
    open_names={normalize_name(name) for name in ShoppingItem.objects.filter(shopping_list__family=family,checked=False).values_list("name",flat=True)}
    grouped=defaultdict(list);labels={};metadata={}
    for event in ShoppingPurchaseEvent.objects.filter(family=family).order_by("purchased_at"):
        grouped[event.normalized_name].append(event.purchased_at);labels[event.normalized_name]=event.name;metadata[event.normalized_name]={"quantity":event.quantity,"category":event.category}
    for key,dates in grouped.items():
        pattern=_pattern(dates)
        if not pattern or pattern["confidence"]<MIN_CONFIDENCE or key in open_names or pattern["due_at"]>now+timedelta(days=DUE_WINDOW_DAYS) or _suppressed(feedback.get((PredictionFeedback.Kind.SHOPPING,key)),now):continue
        result.append({"id":f"shopping:{key}","kind":"shopping","subject_key":key,"title":labels[key],"due_at":pattern["due_at"],"interval_days":pattern["interval_days"],"confidence":pattern["confidence"],"confidence_label":_confidence_label(pattern["confidence"]),"sample_count":pattern["sample_count"],"quantity":metadata[key]["quantity"],"category":metadata[key]["category"]})
    for routine in Routine.objects.filter(family=family,active=True):
        prediction=routine_prediction(routine,now);key=str(routine.id)
        if prediction["confidence"]<MIN_CONFIDENCE or not prediction["expected_at"] or prediction["expected_at"]>now+timedelta(days=DUE_WINDOW_DAYS) or _suppressed(feedback.get((PredictionFeedback.Kind.ROUTINE,key)),now):continue
        result.append({"id":f"routine:{key}","kind":"routine","subject_key":key,"routine_id":key,"title":routine.name,"due_at":prediction["expected_at"],"interval_days":prediction["expected_interval_days"],"confidence":prediction["confidence"],"confidence_label":_confidence_label(prediction["confidence"]),"sample_count":prediction["sample_count"]})
    return sorted(result,key=lambda row:(row["due_at"],-row["confidence"],row["title"].casefold()))[:8]
