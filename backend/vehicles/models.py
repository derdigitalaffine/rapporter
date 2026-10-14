import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from family.models import TimestampedModel


JOURNEY_KINDS = [
    ("unclassified", "Unclassified"),
    ("private", "Private"),
    ("business", "Business"),
    ("commute", "Commute"),
]


class Vehicle(TimestampedModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="vehicles")
    name = models.CharField(max_length=120)
    plate = models.CharField(max_length=24, blank=True)
    manufacturer = models.CharField(max_length=80, blank=True)
    model = models.CharField(max_length=80, blank=True)
    vin = models.CharField(max_length=17, blank=True)
    first_registration = models.DateField(null=True, blank=True)
    fuel_type = models.CharField(max_length=16, choices=[("petrol", "Petrol"), ("diesel", "Diesel"), ("electric", "Electric"), ("hybrid", "Hybrid"), ("other", "Other")], default="petrol")
    odometer = models.DecimalField(max_digits=10, decimal_places=1, default=0)
    notes = models.CharField(max_length=2000, blank=True)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["name", "id"]
        constraints = [models.CheckConstraint(condition=Q(odometer__gte=0), name="vehicle_odometer_positive")]


class FuelEntry(TimestampedModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="fuel_entries")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    request_id = models.UUIDField()
    date = models.DateField()
    odometer = models.DecimalField(max_digits=10, decimal_places=1)
    quantity = models.DecimalField(max_digits=9, decimal_places=3)
    unit = models.CharField(max_length=3, choices=[("l", "Litres"), ("kWh", "kWh")], default="l")
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    full_tank = models.BooleanField(default=True)
    station = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["-date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["vehicle", "request_id"], name="fuel_request_unique"),
            models.CheckConstraint(condition=Q(odometer__gte=0, quantity__gt=0, total_cost__gte=0), name="fuel_values_positive"),
        ]


class Journey(TimestampedModel):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="journeys")
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vehicle_journeys")
    request_id = models.UUIDField()
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    start_odometer = models.DecimalField(max_digits=10, decimal_places=1)
    end_odometer = models.DecimalField(max_digits=10, decimal_places=1, null=True, blank=True)
    purpose = models.CharField(max_length=240, blank=True)
    kind = models.CharField(max_length=16, choices=JOURNEY_KINDS, default="unclassified")
    destination = models.CharField(max_length=240, blank=True)
    business_partner = models.CharField(max_length=240, blank=True)
    note = models.CharField(max_length=1000, blank=True)
    detour_reason = models.CharField(max_length=500, blank=True)
    source = models.CharField(max_length=16, choices=[("tracked", "Tracked"), ("manual", "Manual")], default="tracked")
    review_due_at = models.DateTimeField(null=True, blank=True)
    classified_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=500, blank=True)
    legacy_record = models.BooleanField(default=False)
    distance_m = models.FloatField(default=0)
    point_count = models.PositiveIntegerField(default=0)

    @property
    def review_locked(self):
        return bool(self.ended_at and self.review_due_at and timezone.now() >= self.review_due_at)

    @property
    def needs_review(self):
        if not self.ended_at or self.voided_at:
            return False
        if self.kind == "unclassified":
            return True
        if self.kind == "business":
            return not all((self.destination.strip(), self.business_partner.strip(), self.purpose.strip()))
        return False

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["driver", "kind", "started_at"], name="journey_drv_kind_start_idx"),
            models.Index(fields=["vehicle", "started_at"], name="journey_vehicle_start_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["driver", "request_id"], name="journey_request_unique"),
            models.UniqueConstraint(fields=["driver"], condition=Q(ended_at__isnull=True), name="journey_driver_active_unique"),
            models.UniqueConstraint(fields=["vehicle"], condition=Q(ended_at__isnull=True), name="journey_vehicle_active_unique"),
            models.CheckConstraint(condition=Q(start_odometer__gte=0) & (Q(end_odometer__isnull=True) | Q(end_odometer__gte=models.F("start_odometer"))), name="journey_odometer_valid"),
        ]


class JourneyRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    journey = models.ForeignKey(Journey, on_delete=models.CASCADE, related_name="revisions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="journey_revisions")
    sequence = models.PositiveIntegerField()
    event = models.CharField(max_length=24, choices=[
        ("manual_created", "Manual created"),
        ("classified", "Classified"),
        ("corrected", "Corrected"),
        ("voided", "Voided"),
    ])
    reason = models.CharField(max_length=500, blank=True)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["journey_id", "sequence"]
        constraints = [models.UniqueConstraint(fields=["journey", "sequence"], name="journey_revision_sequence_unique")]


class JourneyPoint(models.Model):
    journey = models.ForeignKey(Journey, on_delete=models.CASCADE, related_name="points")
    sequence = models.PositiveIntegerField()
    timestamp = models.DateTimeField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy = models.FloatField()

    class Meta:
        ordering = ["sequence"]
        constraints = [models.UniqueConstraint(fields=["journey", "sequence"], name="journey_point_sequence_unique")]
