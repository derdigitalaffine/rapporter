from django.conf import settings
from django.db import models
from django.utils import timezone

from family.models import Family, Membership, TimestampedModel


class Expense(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        RECEIPT = "receipt", "Receipt"

    class ReceiptStatus(models.TextChoices):
        NONE = "none", "None"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        REVIEW = "review", "Review"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="expenses")
    title = models.CharField(max_length=180, blank=True)
    merchant = models.CharField(max_length=180, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="EUR")
    paid_by = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="expenses_paid")
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
        ]


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
