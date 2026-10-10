import uuid

from django.conf import settings
from django.db import models


class BabyPrivateMedia(models.Model):
    class Scope(models.TextChoices):
        PREGNANCY = "pregnancy", "Pregnancy"
        DEVELOPMENT = "development", "Development"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="baby_private_media")
    pregnancy = models.ForeignKey("baby.PregnancyJourney", null=True, blank=True, on_delete=models.CASCADE, related_name="private_media")
    baby = models.ForeignKey("baby.BabyProfile", null=True, blank=True, on_delete=models.CASCADE, related_name="private_media")
    scope = models.CharField(max_length=20, choices=Scope.choices)
    storage_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    content_type = models.CharField(max_length=64)
    size_bytes = models.PositiveIntegerField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="baby_private_media")

    class Meta:
        app_label = "baby"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["family", "scope", "created_at"], name="baby_media_family_scope_idx")]
