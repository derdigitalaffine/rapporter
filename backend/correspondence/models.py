from django.conf import settings
from django.db import models


class CorrespondenceReview(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWED = "reviewed", "Reviewed"

    document = models.OneToOneField("documents.Document", on_delete=models.CASCADE, related_name="correspondence_review")
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE, related_name="correspondence_reviews")
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="correspondence_reviews_created")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="correspondence_reviews_updated")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["family", "status", "updated_at"], name="corr_family_status_idx")]
