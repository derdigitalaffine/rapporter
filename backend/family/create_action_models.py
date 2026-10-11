from django.db import models

from .models import Membership, TimestampedModel


class CreateActionPreference(TimestampedModel):
    class LearningScope(models.TextChoices):
        FAMILY = "family", "Family"
        GLOBAL = "global", "Global"

    membership = models.OneToOneField(
        Membership,
        on_delete=models.CASCADE,
        related_name="create_action_preference",
    )
    smart_ranking_enabled = models.BooleanField(default=True)
    context_ranking_enabled = models.BooleanField(default=True)
    time_patterns_enabled = models.BooleanField(default=False)
    direct_mode = models.BooleanField(default=False)
    direct_action_id = models.CharField(max_length=48, blank=True)
    max_quick_actions = models.PositiveSmallIntegerField(default=4)
    pinned_action_ids = models.JSONField(default=list, blank=True)
    hidden_action_ids = models.JSONField(default=list, blank=True)
    manual_order = models.JSONField(default=list, blank=True)
    learning_scope = models.CharField(
        max_length=16,
        choices=LearningScope.choices,
        default=LearningScope.FAMILY,
    )


class CreateActionStat(TimestampedModel):
    membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="create_action_stats",
    )
    # Stable Create registry ID only. No object title, note, amount, document name,
    # care/health detail, or other domain content belongs in this model.
    action_id = models.CharField(max_length=48)
    use_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    context_stats = models.JSONField(default=dict, blank=True)
    time_bucket_stats = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "action_id"],
                name="create_action_stat_member_id_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["membership", "last_used_at"], name="create_stat_member_used_idx"),
        ]


class CreateActionUsageReceipt(TimestampedModel):
    """Short-lived idempotency receipt for successful create signals only."""

    membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="create_action_usage_receipts",
    )
    event_id = models.UUIDField(unique=True)
    action_id = models.CharField(max_length=48)
    origin_page = models.CharField(max_length=32, blank=True)
    context_bucket = models.CharField(max_length=32, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["membership", "created_at"], name="create_receipt_member_at_idx"),
        ]
