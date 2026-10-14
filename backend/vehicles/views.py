import csv
import io
import json
import math
from decimal import Decimal
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from entitlements.services import require_capability
from family.models import Membership

from .models import Journey, JourneyPoint, JourneyRevision, Vehicle
from .serializers import (
    FuelSerializer,
    JourneyClassifySerializer,
    JourneyCorrectionSerializer,
    JourneySerializer,
    JourneyVoidSerializer,
    ManualJourneySerializer,
    PointSerializer,
    PointsSerializer,
    StartSerializer,
    StopSerializer,
    VehicleSerializer,
    validate_business_fields,
)


REVIEW_DAYS = 7


def access(request, family_id):
    family_id = serializers.UUIDField().run_validation(family_id)
    member = get_object_or_404(Membership.objects.select_related("family"), family_id=family_id, user=request.user, family__status="active")
    if member.role not in ("owner", "adult"):
        raise PermissionDenied("adult_required")
    require_capability(request.user, member.family, "vehicles")
    return member.family


def vehicle_access(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle.objects.select_related("family"), pk=vehicle_id, family__memberships__user=request.user)
    access(request, vehicle.family_id)
    return vehicle


def journey_access(request, journey_id, lock=False):
    rows = Journey.objects.select_for_update() if lock else Journey.objects
    # Private by driver even for another owner in the same family.
    journey = get_object_or_404(rows.select_related("vehicle"), pk=journey_id, driver=request.user)
    access(request, journey.vehicle.family_id)
    return journey


def private_response(data, status=200):
    response = Response(data, status=status)
    response["Cache-Control"] = "private, no-store"
    return response


def private_download(content, content_type, filename):
    response = HttpResponse(content, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def journey_snapshot(journey):
    # Intentionally excludes GPS points. Snapshots remain driver-private domain data.
    return dict(JourneySerializer(journey).data)


def record_revision(journey, actor, event, reason, before):
    last = journey.revisions.order_by("-sequence").first()
    return JourneyRevision.objects.create(
        journey=journey,
        actor=actor,
        sequence=(last.sequence + 1) if last else 1,
        event=event,
        reason=reason.strip(),
        before=before,
        after=journey_snapshot(journey),
    )


def review_query():
    return Q(kind="unclassified") | Q(kind="business", destination="") | Q(kind="business", business_partner="") | Q(kind="business", purpose="")


def filtered_journeys(request, vehicle, *, reports=False):
    rows = Journey.objects.filter(vehicle=vehicle, driver=request.user)
    if reports:
        rows = rows.filter(ended_at__isnull=False, voided_at__isnull=True)
    elif request.query_params.get("include_voided") != "1":
        rows = rows.filter(voided_at__isnull=True)
    kind = request.query_params.get("kind")
    if kind:
        if kind not in {"unclassified", "private", "business", "commute"}:
            raise ValidationError({"kind": "invalid_choice"})
        rows = rows.filter(kind=kind)
    review = request.query_params.get("review")
    if review == "open":
        rows = rows.filter(ended_at__isnull=False, voided_at__isnull=True).filter(review_query())
    elif review == "done":
        rows = rows.filter(ended_at__isnull=False, voided_at__isnull=True).exclude(review_query())
    elif review not in (None, "", "all"):
        raise ValidationError({"review": "invalid_choice"})
    for key, lookup in (("from", "started_at__date__gte"), ("to", "started_at__date__lte")):
        raw = request.query_params.get(key)
        if raw:
            value = serializers.DateField().run_validation(raw)
            rows = rows.filter(**{lookup: value})
    return rows


def csv_safe(value):
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def meter_distance(journey):
    if journey.end_odometer is None:
        return Decimal("0")
    return journey.end_odometer - journey.start_odometer


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def vehicles(request):
    family = access(request, request.query_params.get("family"))
    if request.method == "GET":
        return private_response(VehicleSerializer(Vehicle.objects.filter(family=family), many=True).data)
    serializer = VehicleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    serializer.save(family=family)
    return private_response(serializer.data, 201)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def vehicle_detail(request, vehicle_id):
    vehicle_access(request, vehicle_id)
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id)
    if request.data.get("archived") and vehicle.journeys.filter(ended_at__isnull=True).exists():
        return private_response({"code": "active_journey"}, 409)
    serializer = VehicleSerializer(vehicle, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return private_response(serializer.data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def fuel(request, vehicle_id):
    vehicle_access(request, vehicle_id)
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id)
    if request.method == "GET":
        return private_response(FuelSerializer(vehicle.fuel_entries.all()[:500], many=True).data)
    serializer = FuelSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    existing = vehicle.fuel_entries.filter(request_id=serializer.validated_data["request_id"]).first()
    if existing:
        return private_response(FuelSerializer(existing).data)
    if vehicle.archived:
        raise ValidationError("vehicle_archived")
    serializer.save(vehicle=vehicle, recorded_by=request.user)
    if serializer.instance.odometer > vehicle.odometer:
        vehicle.odometer = serializer.instance.odometer
        vehicle.save(update_fields=["odometer", "updated_at"])
    return private_response(serializer.data, 201)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def journeys(request, vehicle_id):
    vehicle_access(request, vehicle_id)
    if request.method == "GET":
        rows = filtered_journeys(request, Vehicle.objects.get(pk=vehicle_id))[:500]
        return private_response(JourneySerializer(rows, many=True).data)
    serializer = StartSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    # Serialise starts across both drivers and vehicles, including PostgreSQL races.
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id)
    existing = Journey.objects.filter(driver=request.user, request_id=serializer.validated_data["request_id"]).first()
    if existing:
        if existing.vehicle_id != vehicle.id:
            return private_response({"code": "request_conflict"}, 409)
        return private_response(JourneySerializer(existing).data)
    if vehicle.archived:
        raise ValidationError("vehicle_archived")
    if Journey.objects.filter(driver=request.user, ended_at__isnull=True).exists() or vehicle.journeys.filter(ended_at__isnull=True).exists():
        return private_response({"code": "active_journey"}, 409)
    if serializer.validated_data["start_odometer"] < vehicle.odometer:
        raise ValidationError({"start_odometer": "odometer_decreased"})
    journey = Journey.objects.create(vehicle=vehicle, driver=request.user, started_at=timezone.now(), **serializer.validated_data)
    return private_response(JourneySerializer(journey).data, 201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def manual_journey(request, vehicle_id):
    vehicle_access(request, vehicle_id)
    serializer = ManualJourneySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    vehicle = Vehicle.objects.select_for_update().get(pk=vehicle_id)
    values = dict(serializer.validated_data)
    reason = values.pop("reason")
    existing = Journey.objects.filter(driver=request.user, request_id=values["request_id"]).first()
    if existing:
        if existing.vehicle_id != vehicle.id or existing.source != "manual":
            return private_response({"code": "request_conflict"}, 409)
        return private_response(JourneySerializer(existing).data)
    if vehicle.archived:
        raise ValidationError("vehicle_archived")
    if Journey.objects.filter(driver=request.user, ended_at__isnull=True).exists() or vehicle.journeys.filter(ended_at__isnull=True).exists():
        return private_response({"code": "active_journey"}, 409)
    now = timezone.now()
    journey = Journey.objects.create(
        vehicle=vehicle,
        driver=request.user,
        source="manual",
        legacy_record=False,
        review_due_at=now,
        classified_at=now if values["kind"] != "unclassified" else None,
        **values,
    )
    if journey.end_odometer > vehicle.odometer:
        vehicle.odometer = journey.end_odometer
        vehicle.save(update_fields=["odometer", "updated_at"])
    record_revision(journey, request.user, "manual_created", reason, {})
    return private_response(JourneySerializer(journey).data, 201)


def distance(a, b):
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat, dlon = lat2 - lat1, math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def journey_detail(request, journey_id):
    journey = journey_access(request, journey_id, lock=True)
    if request.method == "DELETE":
        # Completed journal entries are never hard-deleted through the product API.
        if journey.ended_at is None:
            return private_response({"code": "active_journey"}, 409)
        return private_response({"code": "revision_required"}, 409)
    if request.method == "GET":
        return private_response({**JourneySerializer(journey).data, "points": PointSerializer(journey.points.all(), many=True).data})
    serializer = StopSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if journey.ended_at:
        return private_response(JourneySerializer(journey).data)
    end = serializer.validated_data["end_odometer"]
    if end < journey.start_odometer:
        raise ValidationError({"end_odometer": "odometer_decreased"})
    ended_at = timezone.now()
    journey.ended_at = ended_at
    journey.end_odometer = end
    journey.review_due_at = ended_at + timezone.timedelta(days=REVIEW_DAYS)
    if journey.kind != "unclassified" and not (journey.kind == "business" and not all((journey.destination, journey.business_partner, journey.purpose))):
        journey.classified_at = ended_at
    journey.save(update_fields=["ended_at", "end_odometer", "review_due_at", "classified_at", "updated_at"])
    vehicle = Vehicle.objects.select_for_update().get(pk=journey.vehicle_id)
    if end > vehicle.odometer:
        vehicle.odometer = end
        vehicle.save(update_fields=["odometer", "updated_at"])
    return private_response(JourneySerializer(journey).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def classify_journey(request, journey_id):
    journey = journey_access(request, journey_id, lock=True)
    if not journey.ended_at:
        return private_response({"code": "active_journey"}, 409)
    if journey.voided_at:
        return private_response({"code": "voided_journey"}, 409)
    serializer = JourneyClassifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    reason = values.pop("reason", "").strip()
    first_review = journey.needs_review
    if (journey.review_locked or not first_review) and not reason:
        raise ValidationError({"reason": "correction_reason_required"})
    before = journey_snapshot(journey)
    for field in ("kind", "destination", "business_partner", "purpose", "note", "detour_reason"):
        setattr(journey, field, values[field])
    if journey.kind != "business":
        journey.destination = ""
        journey.business_partner = ""
        journey.detour_reason = ""
    journey.classified_at = timezone.now()
    journey.save(update_fields=["kind", "destination", "business_partner", "purpose", "note", "detour_reason", "classified_at", "updated_at"])
    record_revision(journey, request.user, "classified" if first_review else "corrected", reason, before)
    return private_response(JourneySerializer(journey).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def correct_journey(request, journey_id):
    journey = journey_access(request, journey_id, lock=True)
    if not journey.ended_at:
        return private_response({"code": "active_journey"}, 409)
    if journey.voided_at:
        return private_response({"code": "voided_journey"}, 409)
    serializer = JourneyCorrectionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    values = dict(serializer.validated_data)
    reason = values.pop("reason")
    if journey.source != "manual" and ("started_at" in values or "ended_at" in values):
        raise ValidationError({"started_at": "tracked_time_immutable"})
    candidate = {field: getattr(journey, field) for field in ("kind", "destination", "business_partner", "purpose")}
    candidate.update({key: value for key, value in values.items() if key in candidate})
    validate_business_fields(candidate)
    start = values.get("start_odometer", journey.start_odometer)
    end = values.get("end_odometer", journey.end_odometer)
    if end is None or end < start:
        raise ValidationError({"end_odometer": "odometer_decreased"})
    started = values.get("started_at", journey.started_at)
    ended = values.get("ended_at", journey.ended_at)
    if ended <= started:
        raise ValidationError({"ended_at": "must_follow_start"})
    if ended > timezone.now() + timezone.timedelta(minutes=1):
        raise ValidationError({"ended_at": "future_journey"})
    before = journey_snapshot(journey)
    for field, value in values.items():
        setattr(journey, field, value)
    if journey.kind != "business":
        journey.destination = ""
        journey.business_partner = ""
        journey.detour_reason = ""
    if "kind" in values:
        journey.classified_at = timezone.now() if journey.kind != "unclassified" else None
    journey.save()
    vehicle = Vehicle.objects.select_for_update().get(pk=journey.vehicle_id)
    if journey.end_odometer and journey.end_odometer > vehicle.odometer:
        vehicle.odometer = journey.end_odometer
        vehicle.save(update_fields=["odometer", "updated_at"])
    record_revision(journey, request.user, "corrected", reason, before)
    return private_response(JourneySerializer(journey).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def void_journey(request, journey_id):
    journey = journey_access(request, journey_id, lock=True)
    if not journey.ended_at:
        return private_response({"code": "active_journey"}, 409)
    if journey.voided_at:
        return private_response(JourneySerializer(journey).data)
    serializer = JourneyVoidSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    before = journey_snapshot(journey)
    journey.voided_at = timezone.now()
    journey.void_reason = serializer.validated_data["reason"]
    journey.save(update_fields=["voided_at", "void_reason", "updated_at"])
    record_revision(journey, request.user, "voided", journey.void_reason, before)
    return private_response(JourneySerializer(journey).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def journey_revisions(request, journey_id):
    journey = journey_access(request, journey_id)
    rows = journey.revisions.select_related("actor").all()
    return private_response([
        {
            "id": row.id,
            "sequence": row.sequence,
            "event": row.event,
            "reason": row.reason,
            "created_at": row.created_at,
            "actor_id": row.actor_id,
            "before": row.before,
            "after": row.after,
        }
        for row in rows
    ])


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def journey_suggestions(request, vehicle_id):
    vehicle = vehicle_access(request, vehicle_id)
    rows = Journey.objects.filter(vehicle=vehicle, driver=request.user, voided_at__isnull=True).order_by("-started_at")[:200]
    def unique(field):
        result = []
        seen = set()
        for row in rows:
            value = getattr(row, field, "").strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                result.append(value)
            if len(result) >= 12:
                break
        return result
    return private_response({
        "destinations": unique("destination"),
        "business_partners": unique("business_partner"),
        "purposes": unique("purpose"),
    })


def report_summary(rows):
    totals = {key: Decimal("0") for key in ("business", "private", "commute", "unclassified")}
    open_review = 0
    count = 0
    for journey in rows:
        count += 1
        totals[journey.kind] += meter_distance(journey)
        if journey.needs_review:
            open_review += 1
    return {
        "count": count,
        "open_review": open_review,
        "distance_km": str(sum(totals.values(), Decimal("0")).quantize(Decimal("0.1"))),
        "by_kind_km": {key: str(value.quantize(Decimal("0.1"))) for key, value in totals.items()},
    }


def report_csv(rows):
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["journey_id", "started_at", "ended_at", "kind", "start_odometer_km", "end_odometer_km", "distance_km", "destination", "business_partner", "purpose", "note", "detour_reason", "source", "legacy_record", "review_state"])
    for journey in rows:
        writer.writerow([csv_safe(value) for value in [
            journey.id, journey.started_at.isoformat(), journey.ended_at.isoformat(), journey.kind,
            journey.start_odometer, journey.end_odometer, meter_distance(journey), journey.destination,
            journey.business_partner, journey.purpose, journey.note, journey.detour_reason, journey.source,
            journey.legacy_record, "open" if journey.needs_review else "done",
        ]])
    return "\ufeff" + output.getvalue()


def audit_csv(rows):
    ids = [row.id for row in rows]
    revisions = JourneyRevision.objects.filter(journey_id__in=ids).order_by("journey_id", "sequence")
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["journey_id", "sequence", "event", "created_at", "actor_id", "reason", "before", "after"])
    for revision in revisions:
        writer.writerow([csv_safe(value) for value in [
            revision.journey_id, revision.sequence, revision.event, revision.created_at.isoformat(), revision.actor_id,
            revision.reason, json.dumps(revision.before, ensure_ascii=False, sort_keys=True), json.dumps(revision.after, ensure_ascii=False, sort_keys=True),
        ]])
    return "\ufeff" + output.getvalue()


def report_pdf(vehicle, rows, summary):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title="Fahrtenbuch")
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Fahrtenbuch", styles["Title"]),
        Paragraph(f"Fahrzeug: {vehicle.name} {vehicle.plate}".strip(), styles["Normal"]),
        Paragraph(f"Fahrten: {summary['count']} · Strecke: {summary['distance_km']} km · Noch zuzuordnen: {summary['open_review']}", styles["Normal"]),
        Spacer(1, 5 * mm),
    ]
    data = [["Datum", "Art", "km", "Ziel / Partner", "Zweck"]]
    for journey in rows:
        data.append([
            timezone.localtime(journey.started_at).strftime("%d.%m.%Y %H:%M"),
            journey.kind,
            str(meter_distance(journey)),
            " / ".join(value for value in (journey.destination, journey.business_partner) if value),
            journey.purpose,
        ])
    table = Table(data, repeatRows=1, colWidths=[30 * mm, 24 * mm, 16 * mm, 55 * mm, 55 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([
        table,
        Spacer(1, 5 * mm),
        Paragraph("Hinweis: Dieser Bericht unterstützt die persönliche Dokumentation. Rapporter gibt keine Zusage einer steuerrechtlichen Anerkennung oder Manipulationssicherheit.", styles["Italic"]),
    ])
    document.build(story)
    return buffer.getvalue()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def journey_report(request, vehicle_id):
    vehicle = vehicle_access(request, vehicle_id)
    rows = list(filtered_journeys(request, vehicle, reports=True).order_by("started_at", "id"))
    summary = report_summary(rows)
    format_name = request.query_params.get("format", "json")
    if format_name == "json":
        return private_response({"summary": summary, "journeys": JourneySerializer(rows, many=True).data})
    if format_name == "csv":
        return private_download(report_csv(rows), "text/csv; charset=utf-8", "fahrtenbuch.csv")
    if format_name == "audit":
        return private_download(audit_csv(rows), "text/csv; charset=utf-8", "fahrtenbuch-audit.csv")
    if format_name == "pdf":
        return private_download(report_pdf(vehicle, rows, summary), "application/pdf", "fahrtenbuch.pdf")
    raise ValidationError({"format": "invalid_choice"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def points(request, journey_id):
    journey = journey_access(request, journey_id, lock=True)
    serializer = PointsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    previous = journey.points.order_by("-sequence").first()
    additions = []
    existing_points = {point.sequence: point for point in journey.points.filter(sequence__in=[value["sequence"] for value in serializer.validated_data["points"]])}
    extra_distance = 0
    for values in serializer.validated_data["points"]:
        existing = existing_points.get(values["sequence"])
        if existing:
            if any(getattr(existing, key) != value for key, value in values.items()):
                return private_response({"code": "point_conflict"}, 409)
            continue
        if journey.ended_at:
            return private_response({"code": "journey_finished"}, 409)
        expected = previous.sequence + 1 if previous else 0
        if values["sequence"] != expected or values["timestamp"] < journey.started_at or (previous and values["timestamp"] <= previous.timestamp):
            raise ValidationError("point_order")
        point = JourneyPoint(journey=journey, **values)
        if previous:
            segment = distance(previous, point)
            seconds = (point.timestamp - previous.timestamp).total_seconds()
            if segment / seconds > 80:
                raise ValidationError("implausible_speed")
            extra_distance += segment
        additions.append(point)
        previous = point
    JourneyPoint.objects.bulk_create(additions)
    journey.distance_m += extra_distance
    journey.point_count += len(additions)
    journey.save(update_fields=["distance_m", "point_count", "updated_at"])
    return private_response(JourneySerializer(journey).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def active(request):
    family = access(request, request.query_params.get("family"))
    journey = Journey.objects.filter(driver=request.user, vehicle__family=family, ended_at__isnull=True).first()
    return private_response(JourneySerializer(journey).data if journey else None)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def map_config(request):
    access(request, request.query_params.get("family"))
    template = settings.VEHICLES_OSM_TILE_URL
    parsed = urlparse(template)
    public_osm = template == "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    same_origin = template.startswith("/") and not template.startswith("//") and not parsed.netloc
    valid = (public_osm or same_origin) and "\\" not in template and not any(ord(char) < 32 for char in template) and all(token in template for token in ("{z}", "{x}", "{y}")) and not parsed.query and not parsed.fragment
    if not valid:
        return private_response({"configured": False})
    return private_response({"configured": True, "tile_url": template})
