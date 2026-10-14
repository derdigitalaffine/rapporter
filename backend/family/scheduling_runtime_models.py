from django.db import models

from .models import Family, TimestampedModel


class SchedulingMaterialization(TimestampedModel):
    """Idempotent provenance for a derived scheduling output.

    The referenced domain object remains authoritative.  This row only records
    why/when it was projected or materialized so recalculation can be safely
    deduplicated and explained to the user.
    """

    class Status(models.TextChoices):
        PROJECTED = "projected", "Projected"
        MATERIALIZED = "materialized", "Materialized"
        SKIPPED = "skipped", "Skipped"
        DETACHED = "detached", "Detached"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="scheduling_materializations")
    dependency = models.ForeignKey(
        "SchedulingDependency",
        on_delete=models.CASCADE,
        related_name="materializations",
    )
    anchor_type = models.CharField(max_length=32)
    anchor_id = models.UUIDField()
    anchor_occurrence_key = models.CharField(max_length=96)
    output_type = models.CharField(max_length=32)
    output_id = models.UUIDField(null=True, blank=True)
    scheduled_for = models.DateTimeField()
    dedupe_key = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROJECTED)
    projected_payload = models.JSONField(default=dict, blank=True)
    provenance = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["family", "dedupe_key"], name="schedule_mat_dedupe_unique"),
        ]
        indexes = [
            models.Index(fields=["dependency", "scheduled_for"], name="schedule_mat_dep_time_idx"),
            models.Index(fields=["family", "output_type", "output_id"], name="schedule_mat_output_idx"),
        ]
