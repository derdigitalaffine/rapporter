from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .birthdays import calendar_projection, local_now
from .calendar_recurrence import normalize_event_recurrence, project_event, recurrence_dict
from .models import Family, FamilyEvent, Membership
from .views import FamilyEventViewSet as BaseFamilyEventViewSet


READ_ONLY_EVENT_TYPES = {"school.holiday", "travel.trip"}
MAX_CALENDAR_RANGE_DAYS = 732


def _visible_families(request):
    families = Family.objects.filter(memberships__user=request.user, status="active").distinct()
    family_id = request.query_params.get("family")
    if family_id:
        families = [family for family in families if str(family.id) == family_id]
    else:
        families = list(families)
    return families


def _parse_range(request, default_start):
    try:
        start = date.fromisoformat(request.query_params["start"]) if request.query_params.get("start") else default_start
        end = date.fromisoformat(request.query_params["end"]) if request.query_params.get("end") else start + timedelta(days=366)
        if end < start or (end - start).days > MAX_CALENDAR_RANGE_DAYS:
            raise ValueError()
    except ValueError as exc:
        raise ValidationError("Use a calendar range of at most two years.") from exc
    return start, end


def _family_zone(family):
    try:
        return ZoneInfo(family.timezone or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _effective_family(serializer):
    return serializer.validated_data.get("family") or getattr(serializer.instance, "family", None)


def _effective_event_type(serializer):
    return serializer.validated_data.get("type") or getattr(serializer.instance, "type", None)


def _effective_source(serializer):
    if "source" in serializer.validated_data:
        return serializer.validated_data.get("source")
    return getattr(serializer.instance, "source", None)


def _validate_guardian(target, family, request):
    if target.role != Membership.Role.CHILD or target.user_id == request.user.id:
        return

    from baby.child_identity_service import require_child_membership_guardian

    require_child_membership_guardian(request.user, target)


def _legacy_participant_selection(serializer, family):
    """Map the old payload.member_id write contract to the canonical participant relation."""
    if "participants" in serializer.validated_data or "payload" not in serializer.validated_data:
        return None
    payload = serializer.validated_data.get("payload")
    if not isinstance(payload, dict):
        return None
    member_id = payload.get("member_id")
    if member_id in (None, ""):
        return []
    try:
        normalized = UUID(str(member_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"payload": {"member_id": "Ungültige Personenzuordnung."}}) from exc
    target = Membership.objects.filter(family=family, id=normalized).first() if family else None
    if not target:
        raise ValidationError({"payload": {"member_id": "Person gehört nicht zu dieser Familie."}})
    return [target]


def _validate_event_people(serializer, request):
    """Validate the final native-event participant set and return legacy selection when used."""
    family = _effective_family(serializer)
    event_type = _effective_event_type(serializer)
    legacy_selection = _legacy_participant_selection(serializer, family)

    if "participants" in serializer.validated_data:
        participants = list(serializer.validated_data.get("participants") or [])
    elif legacy_selection is not None:
        participants = legacy_selection
    elif serializer.instance:
        participants = list(serializer.instance.participants.all())
    else:
        participants = []

    is_family_event = serializer.validated_data.get(
        "is_family_event",
        getattr(serializer.instance, "is_family_event", False),
    )
    if event_type != "calendar.event" and (participants or is_family_event):
        raise ValidationError(
            {
                "participants": "Personenzuordnung und Familientermin sind nur für FamilyOS-Kalendertermine verfügbar."
            }
        )

    for target in participants:
        if not family or target.family_id != family.id:
            raise ValidationError({"participants": "Mindestens eine Person gehört nicht zu dieser Familie."})
        _validate_guardian(target, family, request)
    return legacy_selection


def _validate_native_recurrence(serializer):
    family = _effective_family(serializer)
    event_type = _effective_event_type(serializer)
    source = _effective_source(serializer)
    if event_type != "calendar.event" or source is not None or "payload" not in serializer.validated_data:
        return
    payload = serializer.validated_data.get("payload")
    if not isinstance(payload, dict) or "recurrence" not in payload:
        return
    starts_at = serializer.validated_data.get("starts_at") or getattr(serializer.instance, "starts_at", None)
    try:
        recurrence = normalize_event_recurrence(payload.get("recurrence"), starts_at, family.timezone if family else "UTC")
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValidationError({"payload": {"recurrence": str(exc)}}) from exc
    serializer.validated_data["payload"] = {**payload, "recurrence": recurrence}


def _has_recurrence(event):
    payload = event.payload if isinstance(event.payload, dict) else {}
    return recurrence_dict(payload.get("recurrence")) is not None


class FamilyEventViewSet(BaseFamilyEventViewSet):
    """Calendar contract: forecasts/current conditions are weather data, not appointments."""

    queryset = (
        FamilyEvent.objects.select_related("source", "family")
        .prefetch_related("participants")
        .exclude(type__in=["weather.current", "weather.forecast"])
        .all()
        .order_by("starts_at")
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        families = _visible_families(self.request)
        queryset = queryset.filter(family_id__in=[family.id for family in families])
        start_raw = self.request.query_params.get("start")
        end_raw = self.request.query_params.get("end")
        if not start_raw or not end_raw:
            return queryset
        start, end = _parse_range(self.request, date.today())
        include_undated = self.request.query_params.get("include_undated") == "1"
        overlap = None
        recurring = None
        for family in families:
            zone = _family_zone(family)
            starts_at = datetime.combine(start, time.min, zone)
            ends_before = datetime.combine(end + timedelta(days=1), time.min, zone)
            family_overlap = Q(family=family, starts_at__lt=ends_before) & (
                Q(ends_at__gt=starts_at) | Q(ends_at__isnull=True, starts_at__gte=starts_at)
            )
            if include_undated:
                family_overlap |= Q(family=family, starts_at__isnull=True)
            family_recurring = (
                Q(family=family, source__isnull=True, type="calendar.event")
                & Q(payload__recurrence__isnull=False)
                & ~Q(payload__recurrence="")
            )
            overlap = family_overlap if overlap is None else overlap | family_overlap
            recurring = family_recurring if recurring is None else recurring | family_recurring
        if overlap is None:
            return queryset.none()
        return queryset.filter(overlap | recurring).distinct()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        events = list(queryset)
        serialized = list(self.get_serializer(events, many=True).data)
        explicit_range = bool(request.query_params.get("start") and request.query_params.get("end"))
        project_for_list = request.query_params.get("include_undated") == "1"
        projected = []
        for event, row in zip(events, serialized):
            if event.source_id is None and event.type == "calendar.event" and _has_recurrence(event) and (explicit_range or project_for_list):
                start, end = _parse_range(request, local_now(event.family).date())
                projected.extend(project_event(event, row, start, end))
            else:
                projected.append(row)
        projected.sort(key=lambda row: row.get("starts_at") or "9999")

        page = self.paginate_queryset(projected)
        response = self.get_paginated_response(page) if page is not None else Response(projected)
        if request.query_params.get("birthdays") == "0":
            return response
        families = _visible_families(request)
        virtual = []
        if request.query_params.get("page", "1") == "1":
            for family in families:
                start, end = _parse_range(request, local_now(family).date())
                virtual.extend(calendar_projection(family, request.user, start, end))
        if isinstance(response.data, dict):
            response.data["results"].extend(virtual)
            response.data["results"].sort(key=lambda row: row.get("starts_at") or "9999")
            response.data["count"] += len(virtual)
        else:
            response.data.extend(virtual)
            response.data.sort(key=lambda row: row.get("starts_at") or "9999")
        return response

    def perform_create(self, serializer):
        if serializer.validated_data.get("source"):
            raise PermissionDenied("Externe Kalendertermine werden von ihrer Quelle verwaltet.")
        if serializer.validated_data.get("type") in READ_ONLY_EVENT_TYPES:
            raise PermissionDenied("Dieser Termin wird von seinem Fachbereich verwaltet.")
        _validate_native_recurrence(serializer)
        legacy_selection = _validate_event_people(serializer, self.request)
        super().perform_create(serializer)
        if legacy_selection is not None:
            serializer.instance.participants.set(legacy_selection)

    def perform_update(self, serializer):
        if serializer.instance.source_id or serializer.instance.external_id or serializer.validated_data.get("source"):
            raise PermissionDenied("Externe Kalendertermine sind schreibgeschützt.")
        if serializer.instance.type in READ_ONLY_EVENT_TYPES or serializer.validated_data.get("type") in READ_ONLY_EVENT_TYPES:
            raise PermissionDenied("Dieser Termin ist hier schreibgeschützt.")
        _validate_native_recurrence(serializer)
        legacy_selection = _validate_event_people(serializer, self.request)
        super().perform_update(serializer)
        if legacy_selection is not None:
            serializer.instance.participants.set(legacy_selection)

    def perform_destroy(self, instance):
        if instance.source_id or instance.external_id:
            raise PermissionDenied("Externe Kalendertermine sind schreibgeschützt.")
        if instance.type in READ_ONLY_EVENT_TYPES:
            raise PermissionDenied("Dieser Termin muss in seinem Fachbereich gelöscht werden.")
        super().perform_destroy(instance)
