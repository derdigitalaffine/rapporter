import math
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from .models import Vehicle, FuelEntry, Journey, JourneyPoint


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
    class Meta:
        model = Journey
        fields = ["id", "vehicle", "started_at", "ended_at", "start_odometer", "end_odometer", "purpose", "kind", "distance_m", "point_count"]


class StartSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    start_odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0)
    purpose = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=["private", "business", "commute"], default="private")


class StopSerializer(serializers.Serializer):
    end_odometer = serializers.DecimalField(max_digits=10, decimal_places=1, min_value=0)


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
