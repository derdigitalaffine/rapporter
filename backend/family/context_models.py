from django.conf import settings
from django.db import models

from .models import Family, TimestampedModel


class ContextLink(TimestampedModel):
    """Typed metadata edge between two canonical FamilyOS objects.

    Object truth and permissions stay in the source domains. The generic UUIDs
    are intentionally never exposed through Django GenericForeignKey.
    """

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="context_links")
    source_type = models.CharField(max_length=64)
    source_id = models.UUIDField()
    context_type = models.CharField(max_length=64)
    context_id = models.UUIDField()
    relation_key = models.SlugField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_context_links",
    )

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "source_type", "source_id", "context_type", "context_id", "relation_key"],
                name="context_link_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["family", "source_type", "source_id"], name="ctx_link_source_idx"),
            models.Index(fields=["family", "context_type", "context_id"], name="ctx_link_context_idx"),
        ]
