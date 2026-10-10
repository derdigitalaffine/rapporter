from django.conf import settings
from django.db import models

from .models import Family, FamilyEvent, TimestampedModel


class Trip(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="trips")
    title = models.CharField(max_length=160)
    destination = models.CharField(max_length=160, blank=True)
    starts_on = models.DateField()
    ends_on = models.DateField()
    notes = models.TextField(blank=True, max_length=10000)
    archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_family_trips",
    )
    calendar_event = models.OneToOneField(
        FamilyEvent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="travel_trip",
    )

    class Meta:
        ordering = ["archived", "starts_on", "created_at"]
        indexes = [models.Index(fields=["family", "archived", "starts_on"], name="trip_family_start_idx")]


class TripPhoto(TimestampedModel):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="photos")
    key = models.CharField(max_length=32, editable=False)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    caption = models.CharField(max_length=240, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_trip_photos",
    )

    class Meta:
        ordering = ["created_at", "id"]
