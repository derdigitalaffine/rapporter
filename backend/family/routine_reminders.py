"""Local daytime reminders, at most once per cadence and once per 24 hours."""
from datetime import timedelta
from urllib.parse import urlencode

from django.db import transaction
from django.utils import timezone

from .models import Family, Routine, RoutineReminderState
from .models_features import NotificationPreference
from .predictions import _zone, routine_prediction
from .push import send_user_push


def run_routine_reminders(now=None):
    now = now or timezone.now()
    count = 0
    routines = Routine.objects.filter(active=True, reminder_enabled=True, family__status=Family.Status.ACTIVE).select_related("family").prefetch_related("logs")
    for routine in routines:
        if not 9<=now.astimezone(_zone(routine.family)).hour<20:
            continue
        prediction = routine_prediction(routine,now)
        if prediction["status"] not in {"due","overdue"}:
            continue
        for member in routine.family.memberships.select_related("user").filter(user__is_active=True):
            pref = NotificationPreference.objects.filter(membership=member).first()
            if pref and not pref.routines:
                continue
            with transaction.atomic():
                state,_ = RoutineReminderState.objects.get_or_create(routine=routine,membership=member)
                state = RoutineReminderState.objects.select_for_update().get(pk=state.pk)
                if state.snoozed_until and state.snoozed_until>now:
                    continue
                if state.last_sent_at and state.last_sent_at>now-timedelta(hours=24):
                    continue
                if state.last_cycle_at and abs((state.last_cycle_at-prediction["expected_at"]).total_seconds())<60:
                    continue
                english = routine.family.locale.startswith("en")
                body = f"{routine.name}: time for the next run." if english else f"{routine.name}: Zeit für die nächste Ausführung."
                result = send_user_push(member.user,"Routine",body,"/?"+urlencode({"page":"routines","family":routine.family_id,"routine":routine.id}),tag=f"routine:{routine.id}")
                # Retry transient failures on a later scheduler pass.
                if result["sent"]:
                    state.last_sent_at=now
                    state.last_cycle_at=prediction["expected_at"]
                    state.save(update_fields=["last_sent_at","last_cycle_at","updated_at"])
                    count+=1
    return count
