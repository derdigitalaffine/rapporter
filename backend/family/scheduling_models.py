from django.conf import settings
from django.db import models

from .models import Family, TimestampedModel


class SchedulingSeries(TimestampedModel):
    """Stable scheduling identity around an existing domain object.

    ``target_type``/``target_id`` deliberately point at canonical domain objects
    without taking ownership of their lifecycle. The source domain keeps truth
    and permissions for the event/action itself; this model owns only scheduling
    history and relationships.
    """

    class TargetType(models.TextChoices):
        EVENT = "calendar.event", "Calendar event"
        ACTION = "action", "Action"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        ENDED = "ended", "Ended"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="scheduling_series")
    target_type = models.CharField(max_length=32, choices=TargetType.choices)
    target_id = models.UUIDField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    current_version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_scheduling_series",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["family", "target_type", "target_id"],
                name="schedule_series_target_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["family", "target_type", "target_id"], name="schedule_series_target_idx"),
            models.Index(fields=["family", "status"], name="schedule_series_status_idx"),
        ]


class SchedulingRuleVersion(TimestampedModel):
    """Immutable canonical rule snapshot for a series."""

    class ChangeScope(models.TextChoices):
        INITIAL = "initial", "Initial"
        WHOLE = "whole", "Whole series"
        FUTURE = "future", "This and future"

    series = models.ForeignKey(SchedulingSeries, on_delete=models.CASCADE, related_name="rule_versions")
    version = models.PositiveIntegerField()
    rule = models.JSONField()
    change_scope = models.CharField(max_length=16, choices=ChangeScope.choices, default=ChangeScope.INITIAL)
    effective_from = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_scheduling_rule_versions",
    )

    class Meta:
        ordering = ["version"]
        constraints = [
            models.UniqueConstraint(fields=["series", "version"], name="schedule_rule_version_unique"),
            models.CheckConstraint(
                condition=(
                    models.Q(change_scope="future", effective_from__isnull=False)
                    | models.Q(change_scope__in=["initial", "whole"], effective_from__isnull=True)
                ),
                name="schedule_rule_scope_effective_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["series", "effective_from", "version"], name="schedule_rule_effective_idx"),
        ]


class SchedulingOccurrenceOverride(TimestampedModel):
    """Persistent mutation of one otherwise projected occurrence."""

    class Kind(models.TextChoices):
        SKIP = "skip", "Skip"
        OVERRIDE = "override", "Override"
        DETACH = "detach", "Detach"

    series = models.ForeignKey(SchedulingSeries, on_delete=models.CASCADE, related_name="occurrence_overrides")
    occurrence_key = models.CharField(max_length=96)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    payload = models.JSONField(default=dict, blank=True)
    detached_fields = models.JSONField(default=list, blank=True)
    rule_version = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_scheduling_occurrence_overrides",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["series", "occurrence_key"], name="schedule_occurrence_unique"),
        ]
        indexes = [models.Index(fields=["series", "occurrence_key"], name="schedule_occurrence_idx")]


class SchedulingDependency(TimestampedModel):
    """Relative edge from an anchor occurrence/series to a derived output."""

    class AnchorScope(models.TextChoices):
        SERIES = "series", "Series"
        OCCURRENCE = "occurrence", "Occurrence"

    class OutputType(models.TextChoices):
        EVENT = "calendar.event", "Calendar event"
        ACTION = "action", "Action"
        NOTIFICATION = "notification", "Notification"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="scheduling_dependencies")
    anchor_type = models.CharField(max_length=32)
    anchor_id = models.UUIDField()
    anchor_scope = models.CharField(max_length=16, choices=AnchorScope.choices, default=AnchorScope.SERIES)
    anchor_occurrence_key = models.CharField(max_length=96, blank=True)
    output_type = models.CharField(max_length=32, choices=OutputType.choices)
    output_blueprint = models.JSONField(default=dict, blank=True)
    relative_rule = models.JSONField()
    inheritance = models.JSONField(default=dict, blank=True)
    conflict_policy = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_scheduling_dependencies",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(anchor_scope="series", anchor_occurrence_key="")
                    | (models.Q(anchor_scope="occurrence") & ~models.Q(anchor_occurrence_key=""))
                ),
                name="schedule_dependency_scope_key_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["family", "anchor_type", "anchor_id"], name="schedule_dependency_anchor_idx"),
            models.Index(fields=["family", "enabled"], name="schedule_dep_enabled_idx"),
        ]


class SchedulingMaterialization(TimestampedModel):
    """Idempotent provenance for a projected or materialized dependency output."""

    class Status(models.TextChoices):
        PROJECTED = "projected", "Projected"
        MATERIALIZED = "materialized", "Materialized"
        SKIPPED = "skipped", "Skipped"
        DETACHED = "detached", "Detached"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="scheduling_materializations")
    dependency = models.ForeignKey(SchedulingDependency, on_delete=models.CASCADE, related_name="materializations")
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


class SchedulingTemplate(TimestampedModel):
    """Reusable snapshot; changing a template never mutates existing series."""

    class Scope(models.TextChoices):
        PERSONAL = "personal", "Personal"
        FAMILY = "family", "Family"
        ADMIN = "admin", "Admin managed"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="scheduling_templates")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="scheduling_templates",
    )
    scope = models.CharField(max_length=16, choices=Scope.choices, default=Scope.PERSONAL)
    name = models.CharField(max_length=120)
    rule = models.JSONField()
    dependency_blueprint = models.JSONField(default=dict, blank=True)
    locked = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_scheduling_templates",
    )

    class Meta:
        ordering = ["name", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope="personal", owner__isnull=False)
                    | models.Q(scope__in=["family", "admin"], owner__isnull=True)
                ),
                name="schedule_template_scope_owner_valid",
            ),
            models.UniqueConstraint(
                fields=["family", "owner", "name"],
                condition=models.Q(scope="personal"),
                name="schedule_template_personal_name_unique",
            ),
            models.UniqueConstraint(
                fields=["family", "scope", "name"],
                condition=models.Q(scope__in=["family", "admin"]),
                name="schedule_template_shared_name_unique",
            ),
        ]
        indexes = [models.Index(fields=["family", "scope", "name"], name="schedule_template_scope_idx")]
