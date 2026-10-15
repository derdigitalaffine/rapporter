"""Revocable credentials for the canonical family calendar's read-only adapter."""
from django.conf import settings
from django.db import models
from .models import Family, TimestampedModel


class CalendarSubscription(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='calendar_subscriptions')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='calendar_subscriptions')
    name = models.CharField(max_length=80)
    token_digest = models.CharField(max_length=64, unique=True)
    credentials_encrypted = models.TextField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
