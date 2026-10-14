"""Content-free, tenant-private successful domain actions. Never clickstream."""
from django.conf import settings
from django.db import models
from family.models import TimestampedModel

ACTIONS = (
    ("task", "created", "task"), ("task", "completed", "task"),
    ("task", "reopened", "task"), ("routine", "created", "routine"),
    ("routine", "completed", "routine"), ("shopping", "item_added", "shopping_item"),
    ("shopping", "item_purchased", "shopping_item"),
    ("shopping", "list_created", "shopping_list"),
    ("calendar", "event_created", "calendar_event"),
)


class FamilyContributionEvent(TimestampedModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE)
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    actor_membership = models.ForeignKey("family.Membership", null=True, blank=True, on_delete=models.SET_NULL)
    domain = models.CharField(max_length=16)
    action = models.CharField(max_length=24)
    entity_type = models.CharField(max_length=24)
    entity_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField()
    effort_minutes = models.PositiveIntegerField(null=True, blank=True)
    source = models.CharField(max_length=16, choices=[(s, s) for s in ("ui", "automation", "import", "system")])
    idempotency_key = models.CharField(max_length=160)
    schema_version = models.PositiveSmallIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["family", "idempotency_key"], name="stats_event_once"),
            models.CheckConstraint(condition=models.Q(domain="task", action__in=["created", "completed", "reopened"], entity_type="task") | models.Q(domain="routine", action__in=["created", "completed"], entity_type="routine") | models.Q(domain="shopping", action__in=["item_added", "item_purchased"], entity_type="shopping_item") | models.Q(domain="shopping", action="list_created", entity_type="shopping_list") | models.Q(domain="calendar", action="event_created", entity_type="calendar_event"), name="stats_action_allowlist"),
            models.CheckConstraint(condition=models.Q(source__in=["ui", "automation", "import", "system"]), name="stats_source_allowlist"),
        ]
        indexes = [
            models.Index(fields=["family", "occurred_at"], name="stats_family_time_idx"),
            models.Index(fields=["family", "actor_user", "occurred_at"], name="stats_actor_time_idx"),
            models.Index(fields=["family", "domain", "occurred_at"], name="stats_domain_time_idx"),
            models.Index(fields=["family", "entity_type", "entity_id"], name="stats_entity_idx"),
        ]


class FamilyContributionDaily(TimestampedModel):
    family = models.ForeignKey("family.Family", on_delete=models.CASCADE)
    local_date = models.DateField()
    actor_membership = models.ForeignKey("family.Membership", null=True, blank=True, on_delete=models.SET_NULL)
    # A non-null bucket makes unknown actors unique on PostgreSQL too.
    actor_key = models.CharField(max_length=40, default="unknown")
    domain = models.CharField(max_length=16)
    action = models.CharField(max_length=24)
    count = models.PositiveIntegerField(default=0)
    effort_minutes_sum = models.PositiveBigIntegerField(default=0)
    effort_coverage_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["family", "local_date", "actor_key", "domain", "action"], name="stats_daily_unique")]
        indexes = [models.Index(fields=["family", "local_date"], name="stats_daily_range_idx")]
