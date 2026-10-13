import math
from urllib.parse import urlparse
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers
from entitlements.services import require_capability
from family.models import Membership
from .models import Vehicle, Journey, JourneyPoint
from .serializers import VehicleSerializer, FuelSerializer, JourneySerializer, StartSerializer, StopSerializer, PointsSerializer, PointSerializer


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
    journey = get_object_or_404(rows, pk=journey_id, driver=request.user)
    access(request, journey.vehicle.family_id)
    return journey


def private_response(data, status=200):
    response = Response(data, status=status)
    response["Cache-Control"] = "private, no-store"
    return response


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
        return private_response(JourneySerializer(Journey.objects.filter(vehicle_id=vehicle_id, driver=request.user)[:500], many=True).data)
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
        if journey.ended_at is None:
            return private_response({"code": "active_journey"}, 409)
        journey.delete()
        return private_response(None, 204)
    if request.method == "GET":
        return private_response({**JourneySerializer(journey).data, "points": PointSerializer(journey.points.all(), many=True).data})
    serializer = StopSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if journey.ended_at:
        return private_response(JourneySerializer(journey).data)
    end = serializer.validated_data["end_odometer"]
    if end < journey.start_odometer:
        raise ValidationError({"end_odometer": "odometer_decreased"})
    journey.ended_at, journey.end_odometer = timezone.now(), end
    journey.save(update_fields=["ended_at", "end_odometer", "updated_at"])
    vehicle = Vehicle.objects.select_for_update().get(pk=journey.vehicle_id)
    if end > vehicle.odometer:
        vehicle.odometer = end
        vehicle.save(update_fields=["odometer", "updated_at"])
    return private_response(JourneySerializer(journey).data)


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
