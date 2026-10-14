import math
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import FuelEntry, JOURNEY_KINDS, Journey, JourneyPoint, Vehicle


JOURNEY_KIND_VALUES = [value for value, _label in JOURNEY_KINDS]
BUSINESS_REQUIRED = ("destination", "business_partner", "purpose")


def validate_business_fields(values, *, partial=False, current=None):
    kind = values.get("kind", getattr(current, "kind", None))
    if kind != "business":
        return values
    missing = []
    for field in BUSINESS_REQUIRED:
        value = values.get(field, getattr(current, field, "") if current is not None else "")
        if not str(value or "").strip():
            missing.append(field)
    if missing and not partial:
        raise serializers.ValidationError({field: "required_for_business" for field in missing})
    if missing and partial and "kind" in values:
        raise serializers.ValidationError({field: "required_for_business" for field in missing})
    return values


class VehicleSerializer(serializers.ModelSerializer):
    odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0, required=False)

    class Meta:
        model = Vehicle
        fields = ["id", "family", "name", "plate", "manufacturer", "model", "vin", "first_registration", "fuel_type", "odometer", "notes", "archived"]
        read_only_fields = ["id", "family"]

    def validate_vin(self, value):
        value = value.upper().strip()
        if value and (len(value) != 17 or not value.isalnum() or any(c in value for c in "IOQ") or not value.isascii()):
            raise serializers.ValidationError("invalid_vin")
        return value


class FuelSerializer(serializers.ModelSerializer):
    quantity = serializers.DecimalField(max_digits=9, decimal_places=3, min_value=Decimal("0.001"))
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0)
    request_id = serializers.UUIDField()

    class Meta:
        model = FuelEntry
        fields = ["id", "request_id", "vehicle", "date", "odometer", "quantity", "unit", "total_cost", "currency", "full_tank", "station"]
        read_only_fields = ["id", "vehicle"]
        validators = []

    def validate_currency(self, value):
        value = value.upper()
        if len(value) != 3 or not value.isalpha() or not value.isascii():
            raise serializers.ValidationError("invalid_currency")
        return value

    def validate_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("future_date")
        return value


class JourneySerializer(serializers.ModelSerializer):
    review_locked = serializers.BooleanField(read_only=True)
    needs_review = serializers.BooleanField(read_only=True)

    class Meta:
        model = Journey
        fields = [
            "id", "vehicle", "created_at", "updated_at", "started_at", "ended_at",
            "start_odometer", "end_odometer", "purpose", "kind", "destination",
            "business_partner", "note", "detour_reason", "source", "review_due_at",
            "classified_at", "voided_at", "void_reason", "legacy_record", "review_locked",
            "needs_review", "distance_m", "point_count",
        ]
        read_only_fields = fields


class StartSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    start_odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0)
    purpose = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=JOURNEY_KIND_VALUES, default="unclassified")


class StopSerializer(serializers.Serializer):
    end_odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0)


class JourneyClassifySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=JOURNEY_KIND_VALUES)
    destination = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    business_partner = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    purpose = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    detour_reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate(self, values):
        if values["kind"] == "unclassified":
            raise serializers.ValidationError({"kind": "classification_required"})
        return validate_business_fields(values)


class JourneyCorrectionSerializer(serializers.Serializer):
    start_odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0, required=False)
    end_odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0, required=False)
    started_at = serializers.DateTimeField(required=False)
    ended_at = serializers.DateTimeField(required=False)
    kind = serializers.ChoiceField(choices=JOURNEY_KIND_VALUES, required=False)
    destination = serializers.CharField(max_length=240, required=False, allow_blank=True)
    business_partner = serializers.CharField(max_length=240, required=False, allow_blank=True)
    purpose = serializers.CharField(max_length=240, required=False, allow_blank=True)
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    detour_reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    reason = serializers.CharField(max_length=500, required=True, allow_blank=False)

    def validate(self, values):
        editable = set(values) - {"reason"}
        if not editable:
            raise serializers.ValidationError("no_changes")
        return values


class ManualJourneySerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    started_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField()
    start_odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0)
    end_odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0)
    kind = serializers.ChoiceField(choices=JOURNEY_KIND_VALUES, default="unclassified")
    destination = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    business_partner = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    purpose = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    detour_reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=500, required=True, allow_blank=False)

    def validate(self, values):
        if values["ended_at"] <= values["started_at"]:
            raise serializers.ValidationError({"ended_at": "must_follow_start"})
        if values["end_odometer"] < values["start_odometer"]:
            raise serializers.ValidationError({"end_odometer": "odometer_decreased"})
        if values["ended_at"] > timezone.now() + timedelta(minutes=1):
            raise serializers.ValidationError({"ended_at": "future_journey"})
        return validate_business_fields(values)


class JourneyVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=True, allow_blank=False)


class PointSerializer(serializers.ModelSerializer):
    sequence = serializers.IntegerField(min_value=0, max_value=19999)
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    accuracy = serializers.FloatField(min_value=0, max_value=100)

    class Meta:
        model = JourneyPoint
        fields = ["sequence", "timestamp", "latitude", "longitude", "accuracy"]
        validators = []

    def validate(self, values):
        if not all(math.isfinite(values[key]) for key in ("latitude", "longitude", "accuracy")):
            raise serializers.ValidationError("invalid_coordinate")
        if values["timestamp"] > timezone.now() + timedelta(minutes=1):
            raise serializers.ValidationError("future_point")
        return values


class PointsSerializer(serializers.Serializer):
    points = PointSerializer(many=True, allow_empty=False, max_length=100)
