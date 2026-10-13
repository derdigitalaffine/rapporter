from django.db import models

from .models import Family, TimestampedModel


class BirthdayAgePreference(TimestampedModel):
    """Privacy-safe display preference keyed to a projected birthday target."""

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="birthday_age_preferences")
    target_key = models.CharField(max_length=64)
    show_age = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["family", "target_key"], name="birthday_age_preference_target_unique"),
        ]
