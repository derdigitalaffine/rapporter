from django.conf import settings
from django.db import models

from .models import Family, FamilyEvent, Membership, TimestampedModel


class Trip(TimestampedModel):
    class Stage(models.TextChoices):
        IDEA = "idea", "Idea"
        PLANNING = "planning", "Planning"
        SCHEDULED = "scheduled", "Scheduled"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    class DatePrecision(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        YEAR = "year", "Year"
        SEASON = "season", "Season"
        MONTH = "month", "Month"
        RANGE = "range", "Range"
        EXACT = "exact", "Exact"

    class Season(models.TextChoices):
        SPRING = "spring", "Spring"
        SUMMER = "summer", "Summer"
        AUTUMN = "autumn", "Autumn"
        WINTER = "winter", "Winter"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="trips")
    participants = models.ManyToManyField(Membership, related_name="travel_trips", blank=True)
    title = models.CharField(max_length=160)
    destination = models.CharField(max_length=160, blank=True)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.PLANNING)
    date_precision = models.CharField(
        max_length=16,
        choices=DatePrecision.choices,
        default=DatePrecision.EXACT,
    )
    date_year = models.PositiveSmallIntegerField(null=True, blank=True)
    date_month = models.PositiveSmallIntegerField(null=True, blank=True)
    date_season = models.CharField(max_length=8, choices=Season.choices, blank=True)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, max_length=10000)
    # Expand/dual-read compatibility for #170/#229 consumers. `stage` is the
    # richer lifecycle; API writes keep this legacy flag synchronized until a
    # later contract migration removes it.
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
