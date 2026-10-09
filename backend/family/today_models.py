from django.conf import settings
from django.db import models

from .models import Family, TimestampedModel


class TodayLayout(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='today_layouts')
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='today_layouts')
    widgets = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'family'], name='unique_personal_today_layout')]
