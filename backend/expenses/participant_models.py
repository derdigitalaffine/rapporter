from django.db import models

from family.models import Membership, TimestampedModel
from .models import ExpenseBudget


class ExpenseBudgetParticipantPlan(TimestampedModel):
    """Optional participant planning facts; never an ExpenseShare or debt."""

    budget = models.ForeignKey(
        ExpenseBudget,
        on_delete=models.CASCADE,
        related_name="participant_plans",
    )
    member = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="expense_budget_plans",
    )
    spending_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    planned_share = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "member"],
                name="expense_budget_participant_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(spending_limit__isnull=True) | models.Q(spending_limit__gte=0),
                name="expense_budget_limit_nonneg",
            ),
            models.CheckConstraint(
                condition=models.Q(planned_share__isnull=True) | models.Q(planned_share__gte=0),
                name="expense_budget_share_plan_nonneg",
            ),
            models.CheckConstraint(
                condition=models.Q(spending_limit__isnull=False) | models.Q(planned_share__isnull=False),
                name="expense_budget_participant_has_value",
            ),
        ]
