from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from .family_modules import care_access, require_manager, require_module
from .models import PregnancyJourney
from .pregnancy_service import prenatal_calendar_event


@api_view(["GET", "PUT"])
def birth_preferences(request, pregnancy_id):
    pregnancy = PregnancyJourney.objects.select_related("family").filter(pk=pregnancy_id).first()
    if not pregnancy:
        raise NotFound()
    require_module(pregnancy.family)
    care_access(request.user, pregnancy.family, "pregnancy")
    if request.method == "PUT":
        require_manager(request.user, pregnancy.family)
        value = str(request.data.get("birth_preferences") or "")
        if len(value) > 12000:
            raise ValidationError({"birth_preferences": "Birth preferences are limited to 12,000 characters."})
        pregnancy.birth_preferences = value
        pregnancy.save(update_fields=["birth_preferences", "updated_at"])
    return Response({"pregnancy": str(pregnancy.id), "birth_preferences": pregnancy.birth_preferences})


@api_view(["POST"])
def prenatal_event(request, pregnancy_id):
    pregnancy = PregnancyJourney.objects.select_related("family").filter(pk=pregnancy_id).first()
    if not pregnancy:
        raise NotFound()
    require_module(pregnancy.family)
    care_access(request.user, pregnancy.family, "pregnancy")
    title = str(request.data.get("title") or "").strip()
    if not title:
        raise ValidationError({"title": "Title is required."})
    starts_at = serializers.DateTimeField().run_validation(request.data.get("starts_at"))
    ends_at = serializers.DateTimeField(allow_null=True).run_validation(request.data.get("ends_at")) if request.data.get("ends_at") else None
    if ends_at and ends_at < starts_at:
        raise ValidationError({"ends_at": "End must be after start."})
    event_type = str(request.data.get("type") or "baby.prenatal")[:64]
    event = prenatal_calendar_event(
        request.user,
        pregnancy,
        title=title[:180],
        starts_at=starts_at,
        ends_at=ends_at,
        event_type=event_type,
        payload={"note": str(request.data.get("note") or "")[:4000]},
    )
    return Response({"id": str(event.id), "title": event.title, "starts_at": event.starts_at, "ends_at": event.ends_at, "type": event.type}, status=201)
