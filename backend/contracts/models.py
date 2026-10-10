from django.conf import settings
from django.db import models

from family.models import Family, Membership, TimestampedModel


class Contract(TimestampedModel):
    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private"
        FAMILY = "family", "Family"
        SELECTED = "selected", "Selected"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ENDING = "ending", "Ending"
        ENDED = "ended", "Ended"
        CANCELLED = "cancelled", "Cancelled"

    class BillingInterval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        HALF_YEAR = "half_year", "Half year"
        YEARLY = "yearly", "Yearly"
        ONE_TIME = "one_time", "One time"
        OTHER = "other", "Other"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="contracts")
    title = models.CharField(max_length=240)
    category = models.CharField(max_length=96, blank=True)
    provider = models.CharField(max_length=180, blank=True)
    contract_number = models.CharField(max_length=120, blank=True)
    customer_number = models.CharField(max_length=120, blank=True)
    start_date = models.DateField(null=True, blank=True)
    minimum_term_months = models.PositiveIntegerField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    cancellation_period_days = models.PositiveIntegerField(null=True, blank=True)
    renewal_rule = models.CharField(max_length=240, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    billing_interval = models.CharField(max_length=24, choices=BillingInterval.choices, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    notes = models.TextField(blank=True)
    visibility = models.CharField(max_length=16, choices=Visibility.choices, default=Visibility.PRIVATE, db_index=True)
    owner_membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="owned_contracts")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="contracts_created")
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["title", "created_at"]
        indexes = [
            models.Index(fields=["family", "visibility", "archived_at"], name="contract_family_vis_idx"),
            models.Index(fields=["family", "status", "end_date"], name="contract_family_end_idx"),
        ]


class ContractAccess(TimestampedModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="access_entries")
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="contract_access_entries")
    can_view = models.BooleanField(default=True)
    can_manage = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["contract", "membership"], name="contract_access_member_uniq"),
        ]


class ContractReminder(TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="reminders")
    due_on = models.DateField()
    label = models.CharField(max_length=240, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    confirmed_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="contract_reminders_created")

    class Meta:
        ordering = ["due_on", "created_at"]
        indexes = [models.Index(fields=["status", "due_on"], name="contract_reminder_due_idx")]
