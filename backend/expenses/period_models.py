from django.db import models

from family.models import TimestampedModel
from .models import ExpenseBudget


class ExpenseBudgetPeriod(TimestampedModel):
    """Immutable-after-close snapshot of one recurring budget period."""

    class RolloverPolicy(models.TextChoices):
        RESET = "reset", "Reset"
        CARRY_POSITIVE = "carry_positive", "Carry positive remainder"

    budget = models.ForeignKey(
        ExpenseBudget,
        on_delete=models.CASCADE,
        related_name="periods",
    )
    period_type = models.CharField(max_length=16, choices=ExpenseBudget.PeriodType.choices)
    starts_on = models.DateField()
    ends_on = models.DateField()
    planned_amount = models.DecimalField(max_digits=12, decimal_places=2)
    carryover_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rollover_policy = models.CharField(
        max_length=24,
        choices=RolloverPolicy.choices,
        default=RolloverPolicy.RESET,
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-starts_on", "-created_at"]
        indexes = [
            models.Index(fields=["budget", "starts_on", "ends_on"], name="exp_budget_period_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "period_type", "starts_on", "ends_on"],
                name="expense_budget_period_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(planned_amount__gte=0),
                name="expense_budget_period_plan_nonneg",
            ),
            models.CheckConstraint(
                condition=models.Q(carryover_amount__gte=0),
                name="expense_budget_period_carry_nonneg",
            ),
        ]
