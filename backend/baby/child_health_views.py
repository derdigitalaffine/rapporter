from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from auth_sessions.service import require_fresh_session
from telemetry.service import record_audit_event
from .child_identity_service import child_profile, child_scope_access, require_child_guardian, _serialize_guardian_rows
from .child_health_service import health_payload, save_health_record, serialize_record, create_health_reminders
from .family_modules import set_care_circle
from .models import CareCircleAccess, ChildHealthRecord
from .reference_models import PediatricPreventiveEventReference
from .views import CareCircleRow, _serialize_access


class HealthInput(serializers.Serializer):
    key = serializers.RegexField(r"^(exam|vaccination|manual):[A-Za-z0-9_.:-]{1,100}$", max_length=120)
    state = serializers.ChoiceField(choices=["unknown", "planned", "done", "later"])
    expected_version = serializers.IntegerField(min_value=0)
    title = serializers.CharField(required=False, max_length=160, allow_blank=True)
    occurred_on = serializers.DateField(required=False, allow_null=True)
    planned_at = serializers.DateTimeField(required=False, allow_null=True)
    event_starts_at = serializers.DateTimeField(required=False, allow_null=True)
    practice = serializers.CharField(required=False, max_length=160, allow_blank=True)
    note = serializers.CharField(required=False, max_length=4000, allow_blank=True)
    batch = serializers.CharField(required=False, max_length=80, allow_blank=True)
    reference_checksum = serializers.CharField(required=False, max_length=64, allow_blank=True)


class ReminderEntry(serializers.Serializer):
    key = serializers.RegexField(r"^vaccination:[A-Za-z0-9_.:-]{1,100}$", max_length=120)
    expected_version = serializers.IntegerField(min_value=0)
    reference_checksum = serializers.RegexField(r"^[a-f0-9]{64}$")


class ReminderInput(serializers.Serializer):
    entries = ReminderEntry(many=True, min_length=1, max_length=100)
    remind_at = serializers.DateTimeField()

    def validate_entries(self, entries):
        if len({row["key"] for row in entries}) != len(entries):
            raise serializers.ValidationError("Choose each entry once.")
        return entries


@api_view(["POST"])
def child_health_reminders(request, baby_id):
    baby = child_profile(baby_id)
    child_scope_access(request.user, baby, "development")
    serializer = ReminderInput(data=request.data)
    serializer.is_valid(raise_exception=True)
    rows = create_health_reminders(request.user, baby, **serializer.validated_data)
    return Response({"records": [serialize_record(row) for row in rows]})


@api_view(["GET", "POST"])
def child_health(request, baby_id):
    baby = child_profile(baby_id)
    child_scope_access(request.user, baby, "development")
    if request.method == "GET":
        return Response(health_payload(request.user, baby, request.query_params.get("language", "de")))
    entries = request.data.get("entries")
    if entries is not None and (not isinstance(entries, list) or not 1 <= len(entries) <= 100):
        raise serializers.ValidationError({"entries": "Choose between 1 and 100 entries."})
    serializer = HealthInput(data=entries if entries is not None else request.data, many=entries is not None)
    serializer.is_valid(raise_exception=True)
    if entries is not None and not 1 <= len(serializer.validated_data) <= 100:
        raise serializers.ValidationError({"entries": "Choose between 1 and 100 entries."})
    values = serializer.validated_data if entries is not None else [serializer.validated_data]
    if len({row["key"] for row in values}) != len(values):
        raise serializers.ValidationError({"entries": "Choose each entry once."})
    with transaction.atomic():
        saved = [serialize_record(save_health_record(request.user, baby, row)) for row in values]
    return Response({"records": saved})


@api_view(["GET", "PUT"])
def child_care_circle(request, baby_id):
    baby = child_profile(baby_id)
    require_child_guardian(request.user, baby, manage=True)
    if request.method == "PUT":
        require_fresh_session(request)
        serializer = CareCircleRow(data=request.data.get("care_circle", []), many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            set_care_circle(request.user, baby.family, serializer.validated_data, baby=baby)
            record_audit_event("baby.care_circle.changed", actor=request.user, actor_class="user", family=baby.family,
                               target_type="membership" if baby.membership_id else "config",
                               target_id=str(baby.membership_id or baby.id), metadata={"scope": "child"})
    rows = CareCircleAccess.objects.filter(baby=baby).select_related("membership__user").order_by("created_at")
    inherited = CareCircleAccess.objects.filter(family=baby.family, baby__isnull=True).select_related("membership__user")
    return Response({"baby": str(baby.id), "authorities": _serialize_guardian_rows(baby),
                     "care_circle": [_serialize_access(row) for row in rows],
                     "inherited": [_serialize_access(row) for row in inherited if row.can_log_care or row.can_view_growth_development]})


@api_view(["GET"])
def child_health_event(request, event_id):
    from rest_framework.exceptions import NotFound
    reference = PediatricPreventiveEventReference.objects.select_related("baby__family", "baby__membership").filter(event_id=event_id).first()
    if not reference:
        reference = ChildHealthRecord.objects.select_related("baby__family", "baby__membership").filter(event_id=event_id).first()
    if not reference:
        raise NotFound()
    child_scope_access(request.user, reference.baby, "development")
    return Response({"baby": str(reference.baby_id), "family": str(reference.baby.family_id)})
