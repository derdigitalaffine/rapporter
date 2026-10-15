from django.conf import settings
from django.db import models

from family.models import Family, TimestampedModel
from .models import Expense, ExpenseBudget, ExpenseLedger


class BudgetCommitment(TimestampedModel):
    """A reserved amount that reduces availability without becoming an expense.

    Commitments are finance facts. `source_type`/`source_id` only point back to
    the originating domain object (initially a shopping item); they never grant
    access to that object and they never create debt or settlement state.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CONSUMED = "consumed", "Consumed"
        RELEASED = "released", "Released"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="budget_commitments")
    ledger = models.ForeignKey(ExpenseLedger, on_delete=models.PROTECT, related_name="budget_commitments")
    budget = models.ForeignKey(
        ExpenseBudget,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="commitments",
    )
    source_type = models.CharField(max_length=32)
    source_id = models.UUIDField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    consumed_by = models.ForeignKey(
        Expense,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consumed_budget_commitments",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="budget_commitments_created",
    )
    released_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["family", "ledger", "status"], name="exp_commit_ledger_idx"),
            models.Index(fields=["family", "source_type", "source_id"], name="exp_commit_source_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="expense_commit_amount_positive"),
            models.UniqueConstraint(
                fields=["family", "source_type", "source_id"],
                condition=models.Q(status="active"),
                name="expense_commit_active_source_unique",
            ),
        ]
