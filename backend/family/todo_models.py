from django.db import models

from .models import Membership, TimestampedModel


class TodoPreference(TimestampedModel):
    class TodaySort(models.TextChoices):
        SMART = "smart", "Smart"
        CHRONOLOGICAL = "chronological", "Chronological"

    membership = models.OneToOneField(
        Membership,
        on_delete=models.CASCADE,
        related_name="todo_preference",
    )
    smart_ranking_enabled = models.BooleanField(default=True)
    today_sort = models.CharField(
        max_length=16,
        choices=TodaySort.choices,
        default=TodaySort.SMART,
    )


class TodoActionPreference(TimestampedModel):
    membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="todo_action_preferences",
    )
    # Opaque typed projection ID (`task:<uuid>` / `routine:<uuid>`). No title,
    # note, health/document content or usage telemetry is persisted here.
    action_id = models.CharField(max_length=48)
    pinned = models.BooleanField(default=False)
    hidden_from_focus = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "action_id"],
                name="todo_action_pref_member_id_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["membership", "pinned"], name="todo_pref_member_pin_idx"),
        ]
