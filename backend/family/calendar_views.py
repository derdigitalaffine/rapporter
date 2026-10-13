from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError

from .birthdays import calendar_projection, local_now
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


def _validate_member_marker(serializer):
    """Validate the optional Membership id stored in a native event payload."""
    if "payload" not in serializer.validated_data:
        return
    payload = serializer.validated_data.get("payload")
    if not isinstance(payload, dict):
        return
    member_id = payload.get("member_id")
    if member_id in (None, ""):
        return

    event_type = serializer.validated_data.get("type") or getattr(serializer.instance, "type", None)
    if event_type != "calendar.event":
        raise ValidationError({"payload": {"member_id": "Personenzuordnung ist nur für FamilyOS-Kalendertermine verfügbar."}})

    family = serializer.validated_data.get("family") or getattr(serializer.instance, "family", None)
    try:
        normalized = UUID(str(member_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"payload": {"member_id": "Ungültige Personenzuordnung."}}) from exc
    if not family or not Membership.objects.filter(family=family, id=normalized).exists():
        raise ValidationError({"payload": {"member_id": "Person gehört nicht zu dieser Familie."}})


class FamilyEventViewSet(BaseFamilyEventViewSet):
    """Calendar contract: forecasts/current conditions are weather data, not appointments."""

    queryset = FamilyEvent.objects.select_related("source").exclude(type__in=["weather.current", "weather.forecast"]).all().order_by("starts_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        families = _visible_families(self.request)
        queryset = queryset.filter(family_id__in=[family.id for family in families])
        start_raw = self.request.query_params.get("start")
        end_raw = self.request.query_params.get("end")
        # Range filtering is additive. Legacy clients historically supplied zero or
        # one bound and must keep the old paginated-list behavior.
        if not start_raw or not end_raw:
            return queryset
        start, end = _parse_range(self.request, date.today())
        include_undated = self.request.query_params.get("include_undated") == "1"
        overlap = None
        for family in families:
            zone = _family_zone(family)
            starts_at = datetime.combine(start, time.min, zone)
            ends_before = datetime.combine(end + timedelta(days=1), time.min, zone)
            family_overlap = Q(family=family, starts_at__lt=ends_before) & (
                Q(ends_at__gt=starts_at) | Q(ends_at__isnull=True, starts_at__gte=starts_at)
            )
            if include_undated:
                family_overlap |= Q(family=family, starts_at__isnull=True)
            overlap = family_overlap if overlap is None else overlap | family_overlap
        return queryset.filter(overlap) if overlap is not None else queryset.none()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if request.query_params.get("birthdays") == "0":
            return response
        families = _visible_families(request)
        virtual = []
        # Occurrences are included once, on the first page. They are projections,
        # not persisted duplicate FamilyEvent records.
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
        return response

    def perform_create(self, serializer):
        if serializer.validated_data.get("source"):
            raise PermissionDenied("Externe Kalendertermine werden von ihrer Quelle verwaltet.")
        if serializer.validated_data.get("type") in READ_ONLY_EVENT_TYPES:
            raise PermissionDenied("Dieser Termin wird von seinem Fachbereich verwaltet.")
        _validate_member_marker(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        if serializer.instance.source_id or serializer.validated_data.get("source"):
            raise PermissionDenied("Externe Kalendertermine sind schreibgeschützt.")
        if serializer.instance.type in READ_ONLY_EVENT_TYPES or serializer.validated_data.get("type") in READ_ONLY_EVENT_TYPES:
            raise PermissionDenied("Dieser Termin ist hier schreibgeschützt.")
        _validate_member_marker(serializer)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.source_id:
            raise PermissionDenied("Externe Kalendertermine sind schreibgeschützt.")
        if instance.type in READ_ONLY_EVENT_TYPES:
            raise PermissionDenied("Dieser Termin muss in seinem Fachbereich gelöscht werden.")
        super().perform_destroy(instance)
