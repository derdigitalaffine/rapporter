from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from .development_service import development_payload, record_observation
from .family_modules import active_membership, care_access, require_manager, require_module
from .models import BabyProfile, CareCircleAccess, DevelopmentObservation, PregnancyJourney
from .pregnancy_service import archive_pregnancy, complete_birth, create_managed_child
from .template_service import pregnancy_template_items
from .views import AlreadyBornInput, BirthBabyInput, ObservationInput, _serialize_baby, _serialize_pregnancy, requested_family


def _guardian_access(user, family):
    membership = require_manager(user, family)
    access = CareCircleAccess.objects.filter(family=family, membership=membership).first()
    if not access or not access.is_guardian:
        raise PermissionDenied("Managed child identities can only be created by an authorized guardian.")
    return membership, access


@api_view(["PATCH"])
def pregnancy_detail(request, pregnancy_id):
    row = PregnancyJourney.objects.select_related("family").filter(pk=pregnancy_id).first()
    if not row:
        raise NotFound()
    require_module(row.family)
    care_access(request.user, row.family, "pregnancy")
    require_manager(request.user, row.family)
    if "status" in request.data and request.data["status"] in {PregnancyJourney.Status.ARCHIVED, PregnancyJourney.Status.ENDED}:
        archive_pregnancy(request.user, row, status=request.data["status"])
    for field in ("expected_due_date", "start_date", "estimated_from", "notes", "weekly_notification_enabled"):
        if field in request.data:
            if field in {"expected_due_date", "start_date"}:
                parser = serializers.DateField(allow_null=field == "start_date")
                value = parser.run_validation(request.data[field])
            else:
                value = request.data[field]
            setattr(row, field, value)
    row.save()
    return Response(_serialize_pregnancy(row))


@api_view(["POST"])
def pregnancy_birth(request, pregnancy_id):
    row = PregnancyJourney.objects.select_related("family").filter(pk=pregnancy_id).first()
    if not row:
        raise NotFound()
    require_module(row.family)
    care_access(request.user, row.family, "pregnancy")
    _guardian_access(request.user, row.family)
    serializer = BirthBabyInput(data=request.data.get("babies", []), many=True)
    serializer.is_valid(raise_exception=True)
    babies = complete_birth(request.user, row, serializer.validated_data)
    return Response({"babies": [_serialize_baby(baby) for baby in babies]})


@api_view(["POST"])
def pregnancy_templates(request, pregnancy_id):
    row = PregnancyJourney.objects.select_related("family").filter(pk=pregnancy_id).first()
    if not row:
        raise NotFound()
    return Response(pregnancy_template_items(
        request.user,
        row,
        include_tasks=request.data.get("tasks", True),
        include_shopping=request.data.get("shopping", True),
    ))


@api_view(["GET", "POST"])
def baby_profiles(request):
    family = requested_family(request)
    require_module(family)
    membership = active_membership(request.user, family)
    access = CareCircleAccess.objects.filter(family=family, membership=membership).first()
    if not access or not (access.can_log_care or access.can_view_growth_development):
        raise PermissionDenied("Baby profiles are limited to the Care Circle.")
    if request.method == "POST":
        _guardian_access(request.user, family)
        serializer = AlreadyBornInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        baby = create_managed_child(request.user, family, **serializer.validated_data)
        return Response(_serialize_baby(baby), status=201)
    return Response({"babies": [_serialize_baby(row) for row in BabyProfile.objects.filter(family=family, active=True).order_by("birth_date", "created_at")]})


@api_view(["GET", "POST"])
def baby_development(request, baby_id):
    if request.method == "POST":
        serializer = ObservationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = record_observation(request.user, baby_id, **serializer.validated_data)
        return Response({
            "id": str(row.id),
            "state": row.state,
            "milestone_key": row.milestone_key,
            "title": row.title,
            "media_key": row.media_key,
        }, status=201)

    payload = development_payload(request.user, baby_id, language=request.query_params.get("language", "de"))
    custom = DevelopmentObservation.objects.filter(baby_id=baby_id, milestone_key="").order_by("-observed_at", "-created_at")[:100]
    payload["custom_observations"] = [
        {
            "id": str(row.id),
            "title": row.title,
            "state": row.state,
            "observed_at": row.observed_at.isoformat() if row.observed_at else None,
            "note": row.note,
            "media_key": row.media_key,
            "media_url": f"/api/baby/media/{row.media_key}/" if row.media_key else None,
        }
        for row in custom
    ]
    return Response(payload)
