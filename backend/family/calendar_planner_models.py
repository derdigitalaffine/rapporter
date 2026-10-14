from django.conf import settings
from django.db import models

from .models import Family, TimestampedModel


class CalendarPlannerPreference(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="calendar_planner_preferences",
    )
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        related_name="calendar_planner_preferences",
    )
    lane_order = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "family"],
                name="unique_personal_calendar_planner_preference",
            )
        ]
