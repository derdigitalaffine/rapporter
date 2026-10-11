from django.conf import settings
from django.db import models
from django.utils import timezone

from family.models import Family, Membership, TimestampedModel


DEFAULT_LEDGER_NAME = "Familie – laufend"


class ExpenseLedger(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="expense_ledgers")
    name = models.CharField(max_length=120)
    base_currency = models.CharField(max_length=3, default="EUR")
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["family"],
                condition=models.Q(is_default=True),
                name="expense_one_default_ledger",
            ),
            models.CheckConstraint(
                condition=models.Q(budget_amount__isnull=True) | models.Q(budget_amount__gte=0),
                name="expense_ledger_budget_nonneg",
            ),
        ]


def get_default_expense_ledger(family):
    ledger, _ = ExpenseLedger.objects.get_or_create(
        family=family,
        is_default=True,
        defaults={
            "name": DEFAULT_LEDGER_NAME,
            "base_currency": "EUR",
        },
    )
    return ledger


class ExpenseBudget(TimestampedModel):
    class PeriodType(models.TextChoices):
        OPEN = "open", "Open"
        MONTH = "month", "Month"
        YEAR = "year", "Year"
        DATE_RANGE = "date_range", "Date range"
        CONTEXT = "context", "Context"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="expense_budgets")
    ledger = models.ForeignKey(ExpenseLedger, on_delete=models.CASCADE, related_name="budgets")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    period_type = models.CharField(max_length=16, choices=PeriodType.choices, default=PeriodType.OPEN)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["family", "ledger", "archived"], name="exp_budget_ledger_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=0),
                name="expense_budget_amount_nonneg",
            ),
        ]


class Expense(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        RECEIPT = "receipt", "Receipt"

    class FundingSource(models.TextChoices):
        MEMBER = "member", "Member"
        SHARED = "shared", "Shared"

    class ReceiptStatus(models.TextChoices):
        NONE = "none", "None"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        REVIEW = "review", "Review"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="expenses")
    ledger = models.ForeignKey(
        ExpenseLedger,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    title = models.CharField(max_length=180, blank=True)
    merchant = models.CharField(max_length=180, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    # `total_amount`/`currency` are the amount used by debt, settlement and
    # budget math. In explicit FX mode they hold the frozen ledger-base value;
    # original_* + fx_rate preserve the historical source amount/rate.
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="EUR")
    original_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    original_currency = models.CharField(max_length=3, null=True, blank=True)
    fx_rate = models.DecimalField(max_digits=20, decimal_places=10, null=True, blank=True)
    funding_source = models.CharField(
        max_length=16,
        choices=FundingSource.choices,
        default=FundingSource.MEMBER,
    )
    paid_by = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expenses_paid",
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="family_expenses_created")
    client_request_id = models.UUIDField(null=True, blank=True)
    # Expand/migrate/cutover: legacy binary fields remain available for rollback
    # and lazy backfill while all new receipt uploads use the Document Core.
    receipt_document = models.OneToOneField(
        "documents.Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expense_receipt",
    )
    receipt_content = models.BinaryField(null=True, blank=True, editable=False)
    receipt_mime = models.CharField(max_length=64, blank=True)
    receipt_status = models.CharField(max_length=16, choices=ReceiptStatus.choices, default=ReceiptStatus.NONE)
    notes = models.TextField(blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.POSTED, db_index=True)

    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        indexes = [
            models.Index(fields=["family", "currency", "status"], name="exp_family_currency_idx"),
            models.Index(fields=["family", "occurred_at"], name="exp_family_date_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "created_by", "client_request_id"],
                condition=models.Q(client_request_id__isnull=False),
                name="expense_client_request_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(funding_source="member", paid_by__isnull=False)
                    | models.Q(funding_source="shared", paid_by__isnull=True)
                ),
                name="expense_funding_source_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        original_amount__isnull=True,
                        original_currency__isnull=True,
                        fx_rate__isnull=True,
                    )
                    | models.Q(
                        original_amount__isnull=False,
                        original_currency__isnull=False,
                        fx_rate__isnull=False,
                    )
                ),
                name="expense_fx_all_or_none",
            ),
            models.CheckConstraint(
                condition=models.Q(original_amount__isnull=True) | models.Q(original_amount__gt=0),
                name="expense_fx_original_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(fx_rate__isnull=True) | models.Q(fx_rate__gt=0),
                name="expense_fx_rate_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        previous = None
        update_fields = kwargs.get("update_fields")
        tracked_fields = {"ledger", "ledger_id", "total_amount", "currency"}
        should_check = not self._state.adding and (
            update_fields is None or bool(tracked_fields.intersection(update_fields))
        )
        if should_check:
            previous = type(self).objects.filter(pk=self.pk).values(
                "ledger_id",
                "total_amount",
                "currency",
            ).first()
        super().save(*args, **kwargs)
        if previous and (
            previous["ledger_id"] != self.ledger_id
            or previous["total_amount"] != self.total_amount
            or previous["currency"] != self.currency
        ):
            # Budget allocations are optional, but when present they must cover
            # the current expense exactly. Never leave stale allocations after
            # a scope/amount change; the caller may assign a new budget after.
            self.budget_allocations.all().delete()


class ExpenseShare(TimestampedModel):
    class SplitType(models.TextChoices):
        EQUAL = "equal", "Equal"
        EXACT = "exact", "Exact"
        PERCENTAGE = "percentage", "Percentage"
        SHARES = "shares", "Shares"

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="shares")
    member = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="expense_shares")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    split_type = models.CharField(max_length=16, choices=SplitType.choices, default=SplitType.EQUAL)
    split_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        unique_together = ("expense", "member")
        ordering = ["created_at"]


class ExpenseBudgetAllocation(TimestampedModel):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="budget_allocations")
    budget = models.ForeignKey(ExpenseBudget, on_delete=models.CASCADE, related_name="allocations")
    amount_in_budget_currency = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["expense", "budget"],
                name="expense_budget_allocation_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_in_budget_currency__gt=0),
                name="expense_budget_allocation_positive",
            ),
        ]


class ReceiptExtraction(TimestampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        REVIEW = "review", "Review"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    expense = models.OneToOneField(Expense, on_delete=models.CASCADE, related_name="extraction")
    processing_run = models.ForeignKey(
        "documents.DocumentProcessingRun",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="receipt_extractions",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    merchant = models.CharField(max_length=180, blank=True)
    date = models.DateField(null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tax = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    raw_text = models.TextField(blank=True)
    structured_data = models.JSONField(default=dict, blank=True)
    field_confidences = models.JSONField(default=dict, blank=True)
    parser_version = models.CharField(max_length=32, default="receipt-v1")
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)


class Settlement(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="expense_settlements")
    ledger = models.ForeignKey(
        ExpenseLedger,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="settlements",
    )
    from_member = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="settlements_sent")
    to_member = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="settlements_received")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    settled_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="family_settlements_created")
    note = models.CharField(max_length=240, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-settled_at", "-created_at"]
        indexes = [models.Index(fields=["family", "currency", "voided_at"], name="settle_family_currency_idx")]
