from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from family.models import Family, Membership

from .care_service import (
    care_summary,
    care_timeline,
    create_handover,
    handover_payload,
    mark_viewed,
    record_care_log,
    undo_care_log,
    update_care_log,
)
from .development_service import add_appointment_question, development_payload, ensure_u_exam_events, record_observation
from .family_modules import MODULE_KEY, active_membership, care_access, module_setting, require_manager, require_module, set_care_circle, set_module
from .growth_service import add_measurement, growth_payload, set_reference
from .models import (
    BabyCareLog,
    BabyProfile,
    CareCircleAccess,
    FamilyModuleSetting,
    PregnancyBaby,
    PregnancyJournalEntry,
    PregnancyJourney,
    PregnancyUtilitySession,
)
from .pregnancy_service import archive_pregnancy, complete_birth, create_managed_child, create_pregnancy, pregnancy_progress, pregnancy_template_items
from .report_service import audited_export


class ModuleInput(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    show_in_main_navigation = serializers.BooleanField(required=False)


class CareCircleRow(serializers.Serializer):
    membership = serializers.UUIDField()
    can_view_pregnancy = serializers.BooleanField(default=False)
    can_log_care = serializers.BooleanField(default=False)
    can_view_growth_development = serializers.BooleanField(default=False)
    is_guardian = serializers.BooleanField(default=False)


class PregnancyInput(serializers.Serializer):
    expected_due_date = serializers.DateField()
    baby_count = serializers.IntegerField(min_value=1, max_value=3, default=1)
    estimated_from = serializers.ChoiceField(choices=PregnancyJourney.EstimatedFrom.values, default=PregnancyJourney.EstimatedFrom.MANUAL)
    start_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=12000)
    weekly_notification_enabled = serializers.BooleanField(default=False)


class BirthBabyInput(serializers.Serializer):
    pregnancy_baby = serializers.UUIDField()
    display_name = serializers.CharField(max_length=80)
    birth_date = serializers.DateField()
    birth_time = serializers.TimeField(required=False, allow_null=True)
    gestational_age_weeks = serializers.IntegerField(required=False, allow_null=True, min_value=20, max_value=44)
    gestational_age_days = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=6)
    birth_weight_g = serializers.IntegerField(required=False, allow_null=True, min_value=300, max_value=10000)
    birth_length_cm = serializers.DecimalField(required=False, allow_null=True, max_digits=5, decimal_places=2, min_value=20, max_value=80)
    birth_head_circumference_cm = serializers.DecimalField(required=False, allow_null=True, max_digits=5, decimal_places=2, min_value=20, max_value=60)
    growth_reference_sex = serializers.ChoiceField(choices=BabyProfile.ReferenceSex.values, default=BabyProfile.ReferenceSex.UNSPECIFIED)


class AlreadyBornInput(BirthBabyInput):
    pregnancy_baby = None
    client_identity_key = serializers.UUIDField()


class CareLogInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=BabyCareLog.Kind.values)
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(required=False, allow_null=True)
    value = serializers.JSONField(required=False)
    client_event_id = serializers.UUIDField(required=False, allow_null=True)


class CareLogUpdate(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False, allow_null=True)
    value = serializers.JSONField(required=False)


class GrowthInput(serializers.Serializer):
    measured_at = serializers.DateTimeField()
    weight_g = serializers.IntegerField(required=False, allow_null=True)
    length_cm = serializers.DecimalField(required=False, allow_null=True, max_digits=5, decimal_places=2)
    head_circumference_cm = serializers.DecimalField(required=False, allow_null=True, max_digits=5, decimal_places=2)
    source = serializers.ChoiceField(choices=[x[0] for x in BabyProfile._meta.get_field("growth_reference_sex").choices], required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class ObservationInput(serializers.Serializer):
    milestone_key = serializers.CharField(required=False, allow_blank=True, max_length=96)
    title = serializers.CharField(required=False, allow_blank=True, max_length=160)
    state = serializers.ChoiceField(choices=["observed", "not_observed", "later"], default="observed")
    observed_at = serializers.DateTimeField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    media_key = serializers.CharField(required=False, allow_blank=True, max_length=180)


class HandoverInput(serializers.Serializer):
    from_at = serializers.DateTimeField()
    to_at = serializers.DateTimeField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=4000)


def requested_family(request):
    value = request.query_params.get("family") or request.data.get("family")
    try:
        family = Family.objects.filter(pk=value, status=Family.Status.ACTIVE, memberships__user=request.user).first()
    except (ValueError, DjangoValidationError):
        family = None
    if not family:
        raise NotFound("Family not found.")
    return family


def _serialize_access(row):
    return {
        "id": str(row.id),
        "membership": str(row.membership_id),
        "display_name": row.membership.display_name or row.membership.user.get_username(),
        "role": row.membership.role,
        "can_view_pregnancy": row.can_view_pregnancy,
        "can_log_care": row.can_log_care,
        "can_view_growth_development": row.can_view_growth_development,
        "is_guardian": row.is_guardian,
    }


def _serialize_pregnancy(row):
    return {
        "id": str(row.id),
        "status": row.status,
        "expected_due_date": row.expected_due_date.isoformat(),
        "estimated_from": row.estimated_from,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "notes": row.notes,
        "weekly_notification_enabled": row.weekly_notification_enabled,
        "progress": pregnancy_progress(row),
        "babies": [
            {"id": str(b.id), "stable_label": b.stable_label, "display_name": b.display_name, "status": b.status, "order_index": b.order_index}
            for b in row.expected_babies.all()
        ],
    }


def _serialize_baby(row):
    return {
        "id": str(row.id),
        "membership": str(row.membership_id) if row.membership_id else None,
        "display_name": row.display_name,
        "birth_date": row.birth_date.isoformat(),
        "birth_time": row.birth_time.isoformat() if row.birth_time else None,
        "gestational_age_weeks": row.gestational_age_weeks,
        "gestational_age_days": row.gestational_age_days,
        "birth_weight_g": row.birth_weight_g,
        "birth_length_cm": float(row.birth_length_cm) if row.birth_length_cm is not None else None,
        "birth_head_circumference_cm": float(row.birth_head_circumference_cm) if row.birth_head_circumference_cm is not None else None,
        "growth_reference_sex": row.growth_reference_sex,
        "source_pregnancy": str(row.source_pregnancy_id) if row.source_pregnancy_id else None,
        "source_pregnancy_baby": str(row.source_pregnancy_baby_id) if row.source_pregnancy_baby_id else None,
    }


def _serialize_care(row):
    return {
        "id": str(row.id), "kind": row.kind, "started_at": row.started_at.isoformat(),
        "ended_at": row.ended_at.isoformat() if row.ended_at else None, "value": row.value,
        "version": row.version, "created_at": row.created_at.isoformat(), "created_by": row.created_by_id,
    }


@api_view(["GET", "PATCH", "DELETE"])
def module_detail(request):
    family = requested_family(request)
    membership = active_membership(request.user, family)
    setting = module_setting(family)
    access = CareCircleAccess.objects.filter(family=family, membership=membership).first() if setting.enabled else None
    if request.method == "GET":
        can_manage = membership.role in {Membership.Role.OWNER, Membership.Role.ADULT}
        return Response({
            "key": MODULE_KEY,
            "enabled": setting.enabled,
            "show_in_main_navigation": setting.show_in_main_navigation,
            "authorized": bool(access and (access.can_view_pregnancy or access.can_log_care or access.can_view_growth_development)),
            "can_manage": can_manage,
            "permissions": _serialize_access(access) if access else None,
        })
    require_manager(request.user, family)
    if request.method == "DELETE":
        if request.data.get("confirm") != "DELETE":
            raise ValidationError({"confirm": "Send DELETE to permanently remove Pregnancy & Baby tracking data."})
        with transaction.atomic():
            # Managed child User/Membership/UserProfile identities deliberately survive domain deletion.
            BabyProfile.objects.filter(family=family).delete()
            PregnancyJourney.objects.filter(family=family).delete()
            CareCircleAccess.objects.filter(family=family).delete()
            FamilyModuleSetting.objects.filter(family=family, module_key=MODULE_KEY).delete()
        return Response(status=204)
    serializer = ModuleInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    setting = set_module(
        request.user,
        family,
        enabled=serializer.validated_data.get("enabled", setting.enabled),
        show_in_main_navigation=serializer.validated_data.get("show_in_main_navigation"),
    )
    return Response({"key": MODULE_KEY, "enabled": setting.enabled, "show_in_main_navigation": setting.show_in_main_navigation})


@api_view(["GET", "PUT"])
def care_circle(request):
    family = requested_family(request)
    require_manager(request.user, family)
    require_module(family)
    if request.method == "PUT":
        serializer = CareCircleRow(data=request.data.get("care_circle", []), many=True)
        serializer.is_valid(raise_exception=True)
        set_care_circle(request.user, family, serializer.validated_data)
    rows = CareCircleAccess.objects.filter(family=family).select_related("membership__user").order_by("membership__display_name")
    return Response({"care_circle": [_serialize_access(row) for row in rows]})


@api_view(["GET", "POST"])
def pregnancies(request):
    family = requested_family(request)
    require_module(family)
    care_access(request.user, family, "pregnancy")
    if request.method == "POST":
        require_manager(request.user, family)
        serializer = PregnancyInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = create_pregnancy(request.user, family, **serializer.validated_data)
        return Response(_serialize_pregnancy(row), status=201)
    rows = PregnancyJourney.objects.filter(family=family).prefetch_related("expected_babies")
    return Response({"pregnancies": [_serialize_pregnancy(row) for row in rows]})


@api_view(["PATCH"])
def pregnancy_detail(request, pregnancy_id):
    row = PregnancyJourney.objects.select_related("family").filter(pk=pregnancy_id).first()
    if not row:
        raise NotFound()
    require_module(row.family)
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
    serializer = BirthBabyInput(data=request.data.get("babies", []), many=True)
    serializer.is_valid(raise_exception=True)
    babies = complete_birth(request.user, row, serializer.validated_data)
    return Response({"babies": [_serialize_baby(baby) for baby in babies]})


@api_view(["POST"])
def pregnancy_templates(request, pregnancy_id):
    row = PregnancyJourney.objects.select_related("family").filter(pk=pregnancy_id).first()
    if not row:
        raise NotFound()
    return Response(pregnancy_template_items(request.user, row, include_tasks=request.data.get("tasks", True), include_shopping=request.data.get("shopping", True)))


@api_view(["GET", "POST"])
def pregnancy_utilities(request, pregnancy_id):
    row = PregnancyJourney.objects.select_related("family").filter(pk=pregnancy_id).first()
    if not row:
        raise NotFound()
    require_module(row.family)
    care_access(request.user, row.family, "pregnancy")
    if request.method == "POST":
        kind = request.data.get("kind")
        if kind not in PregnancyUtilitySession.Kind.values:
            raise ValidationError({"kind": "Use kick or contraction."})
        started_at = serializers.DateTimeField().run_validation(request.data.get("started_at") or timezone.now().isoformat())
        ended_at = serializers.DateTimeField(allow_null=True).run_validation(request.data.get("ended_at")) if "ended_at" in request.data else None
        client_id = serializers.UUIDField(allow_null=True).run_validation(request.data.get("client_event_id")) if request.data.get("client_event_id") else None
        if client_id:
            existing = PregnancyUtilitySession.objects.filter(pregnancy=row, client_event_id=client_id).first()
            if existing:
                return Response({"id": str(existing.id), "kind": existing.kind, "started_at": existing.started_at, "ended_at": existing.ended_at, "value": existing.value})
        session = PregnancyUtilitySession.objects.create(pregnancy=row, kind=kind, started_at=started_at, ended_at=ended_at, value=request.data.get("value") or {}, created_by=request.user, client_event_id=client_id)
        return Response({"id": str(session.id), "kind": session.kind, "started_at": session.started_at, "ended_at": session.ended_at, "value": session.value}, status=201)
    rows = row.utility_sessions.all()[:200]
    return Response({"sessions": [{"id": str(x.id), "kind": x.kind, "started_at": x.started_at, "ended_at": x.ended_at, "value": x.value} for x in rows]})


@api_view(["PATCH"])
def pregnancy_utility_detail(request, session_id):
    session = PregnancyUtilitySession.objects.select_related("pregnancy__family").filter(pk=session_id).first()
    if not session:
        raise NotFound()
    care_access(request.user, session.pregnancy.family, "pregnancy")
    if "ended_at" in request.data:
        session.ended_at = serializers.DateTimeField(allow_null=True).run_validation(request.data["ended_at"])
    if "value" in request.data:
        session.value = request.data["value"] or {}
    session.save()
    return Response({"id": str(session.id), "kind": session.kind, "started_at": session.started_at, "ended_at": session.ended_at, "value": session.value})


@api_view(["GET", "POST"])
def pregnancy_journal(request, pregnancy_id):
    row = PregnancyJourney.objects.select_related("family").filter(pk=pregnancy_id).first()
    if not row:
        raise NotFound()
    care_access(request.user, row.family, "pregnancy")
    if request.method == "POST":
        entry_date = serializers.DateField().run_validation(request.data.get("entry_date") or timezone.localdate().isoformat())
        expected_baby = None
        if request.data.get("pregnancy_baby"):
            expected_baby = PregnancyBaby.objects.filter(pk=request.data["pregnancy_baby"], pregnancy=row).first()
            if not expected_baby:
                raise ValidationError({"pregnancy_baby": "Expected baby not found in this pregnancy."})
        entry = PregnancyJournalEntry.objects.create(pregnancy=row, pregnancy_baby=expected_baby, entry_date=entry_date, note=str(request.data.get("note") or "")[:12000], media_key=str(request.data.get("media_key") or "")[:180], created_by=request.user)
        return Response({"id": str(entry.id), "entry_date": entry.entry_date, "note": entry.note, "media_key": entry.media_key, "pregnancy_baby": entry.pregnancy_baby_id}, status=201)
    return Response({"entries": [{"id": str(x.id), "entry_date": x.entry_date, "note": x.note, "media_key": x.media_key, "pregnancy_baby": x.pregnancy_baby_id} for x in row.journal_entries.all()[:200]]})


@api_view(["GET", "POST"])
def baby_profiles(request):
    family = requested_family(request)
    require_module(family)
    membership = active_membership(request.user, family)
    access = CareCircleAccess.objects.filter(family=family, membership=membership).first()
    if not access or not (access.can_log_care or access.can_view_growth_development):
        raise PermissionDenied("Baby profiles are limited to the Care Circle.")
    if request.method == "POST":
        require_manager(request.user, family)
        serializer = AlreadyBornInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        baby = create_managed_child(request.user, family, **serializer.validated_data)
        return Response(_serialize_baby(baby), status=201)
    return Response({"babies": [_serialize_baby(row) for row in BabyProfile.objects.filter(family=family, active=True).order_by("birth_date", "created_at")]})


@api_view(["GET", "POST"])
def baby_care(request, baby_id):
    if request.method == "POST":
        serializer = CareLogInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        row, created = record_care_log(request.user, baby_id, **serializer.validated_data)
        return Response(_serialize_care(row), status=201 if created else 200)
    start = serializers.DateTimeField().run_validation(request.query_params["start"]) if request.query_params.get("start") else None
    end = serializers.DateTimeField().run_validation(request.query_params["end"]) if request.query_params.get("end") else None
    rows = care_timeline(request.user, baby_id, start=start, end=end, limit=request.query_params.get("limit", 200))
    return Response({"events": [_serialize_care(row) for row in rows], "summary": care_summary(request.user, baby_id, hours=request.query_params.get("hours", 24))})


@api_view(["PATCH", "DELETE"])
def baby_care_detail(request, care_id):
    if request.method == "DELETE":
        undo_care_log(request.user, care_id)
        return Response(status=204)
    serializer = CareLogUpdate(data=request.data)
    serializer.is_valid(raise_exception=True)
    row = update_care_log(request.user, care_id, **serializer.validated_data)
    return Response(_serialize_care(row))


@api_view(["POST"])
def baby_mark_viewed(request, baby_id):
    state = mark_viewed(request.user, baby_id)
    return Response({"last_viewed_at": state.last_viewed_at})


@api_view(["GET", "POST"])
def baby_growth(request, baby_id):
    if request.method == "POST":
        data = request.data.copy()
        source = data.pop("source", "home")
        serializer = GrowthInput(data=data)
        serializer.is_valid(raise_exception=True)
        row = add_measurement(request.user, baby_id, source=source, **serializer.validated_data)
        return Response({"id": str(row.id)}, status=201)
    return Response(growth_payload(request.user, baby_id))


@api_view(["PATCH"])
def baby_growth_reference(request, baby_id):
    setting = set_reference(request.user, baby_id, reference_key=request.data.get("reference_key"), corrected_age_enabled=request.data.get("corrected_age_enabled"))
    return Response({"reference_key": setting.reference_key, "reference_version": setting.reference_version, "corrected_age_enabled": setting.corrected_age_enabled})


@api_view(["GET", "POST"])
def baby_development(request, baby_id):
    if request.method == "POST":
        serializer = ObservationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = record_observation(request.user, baby_id, **serializer.validated_data)
        return Response({"id": str(row.id), "state": row.state, "milestone_key": row.milestone_key, "title": row.title}, status=201)
    return Response(development_payload(request.user, baby_id, language=request.query_params.get("language", "de")))


@api_view(["POST"])
def baby_preventive_events(request, baby_id):
    rows = ensure_u_exam_events(request.user, baby_id)
    return Response({"events": [{"id": str(row.id), "title": row.title, "starts_at": row.starts_at, "payload": row.payload} for row in rows]})


@api_view(["POST"])
def baby_appointment_question(request, baby_id):
    row = add_appointment_question(request.user, baby_id, event_id=request.data.get("event"), text=request.data.get("text"))
    return Response({"id": str(row.id), "event": str(row.event_id), "text": row.text}, status=201)


@api_view(["POST"])
def baby_handover(request, baby_id):
    serializer = HandoverInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    row = create_handover(request.user, baby_id, **serializer.validated_data)
    return Response({"id": str(row.id), "from_at": row.from_at, "to_at": row.to_at, "note": row.note}, status=201)


@api_view(["GET"])
def baby_handover_detail(request, handover_id):
    return Response(handover_payload(request.user, handover_id))


@api_view(["GET"])
def baby_cockpit(request, baby_id):
    summary = care_summary(request.user, baby_id, hours=request.query_params.get("hours", 24))
    return Response({"now": summary, "actions": ["breastfeed", "bottle", "diaper", "sleep", "pump", "temperature", "medication", "note"]})


@api_view(["GET"])
def baby_report(request, baby_id):
    start = serializers.DateTimeField().run_validation(request.query_params["start"]) if request.query_params.get("start") else None
    end = serializers.DateTimeField().run_validation(request.query_params["end"]) if request.query_params.get("end") else None
    sections = [x for x in request.query_params.get("sections", "").split(",") if x] or None
    export_format = request.query_params.get("format", "json")
    payload, body, content_type = audited_export(request.user, baby_id, export_format=export_format, start=start, end=end, sections=sections, language=request.query_params.get("language", "de"))
    if export_format == "json":
        return Response(body)
    response = HttpResponse(body, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="familyos-baby-report-{baby_id}.{export_format}"'
    return response
