from datetime import timedelta

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import Membership
from .models_features import PredictionFeedback
from .predictions import predictions_for


def _context(request):
    family_id=request.query_params.get("family") or request.data.get("family");membership=Membership.objects.filter(user=request.user,family_id=family_id).select_related("family").first() if family_id else Membership.objects.filter(user=request.user).select_related("family").first()
    if family_id and not membership:raise PermissionDenied("Familie ist für diesen Benutzer nicht verfügbar.")
    return (membership.family,membership) if membership else (None,None)

@api_view(["GET"])
def predictions(request):
    family,membership=_context(request)
    return Response({"suggestions":predictions_for(family,membership) if family else []})

@api_view(["POST"])
def prediction_feedback(request):
    family,membership=_context(request)
    if not family:raise PermissionDenied()
    kind=request.data.get("kind");subject_key=str(request.data.get("subject_key") or "").strip();action=request.data.get("action")
    if kind not in PredictionFeedback.Kind.values or not subject_key:raise ValidationError({"detail":"Ungültige Vorhersage."})
    if action not in {"accept","dismiss","snooze"}:raise ValidationError({"action":"Unbekannte Aktion."})
    row,_=PredictionFeedback.objects.get_or_create(family=family,membership=membership,kind=kind,subject_key=subject_key);row.last_action=action
    if action in {"accept","dismiss"}:row.dismissed=True;row.snoozed_until=None
    else:
        try:days=int(request.data.get("days") or 3)
        except (TypeError,ValueError):raise ValidationError({"days":"Ungültige Dauer."})
        days=max(1,min(days,30));row.dismissed=False;row.snoozed_until=timezone.now()+timedelta(days=days)
    row.save(update_fields=["last_action","dismissed","snoozed_until","updated_at"]);return Response({"ok":True,"action":action,"snoozed_until":row.snoozed_until})
