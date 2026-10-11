from django.conf import settings
from django.db import models

from .models import Family, Membership, TimestampedModel


class NotificationPreference(TimestampedModel):
    membership = models.OneToOneField(Membership, on_delete=models.CASCADE, related_name="notification_preference")
    detail_level = models.CharField(max_length=16, choices=[("important", "Important only"), ("summary", "Summaries"), ("all", "All details")], default="summary")
    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_start = models.TimeField(default="22:00")
    quiet_end = models.TimeField(default="07:00")
    tasks = models.BooleanField(default=True)
    task_assigned = models.BooleanField(default=True)
    shopping = models.BooleanField(default=True)
    calendar = models.BooleanField(default=True)
    family_updates = models.BooleanField(default=True)
    messages = models.BooleanField(default=True)
    routines = models.BooleanField(default=True)
    birthdays = models.BooleanField(default=True)
    birthday_prepare = models.BooleanField(default=True)


class LoyaltyCard(TimestampedModel):
    """Backward-compatible persistence model for the generic Cards & Tickets core.

    The historic table and API name intentionally stay stable. `pass_type` broadens the
    record into the PassItem spectrum without changing barcode payload/symbology or ACLs.
    """

    class BarcodeFormat(models.TextChoices):
        CODE128 = "code128", "Code 128"
        EAN13 = "ean13", "EAN-13"
        EAN8 = "ean8", "EAN-8"
        UPCA = "upca", "UPC-A"
        UPCE = "upce", "UPC-E"
        CODE39 = "code39", "Code 39"
        ITF = "itf", "Interleaved 2 of 5"
        QR = "qrcode", "QR Code"
        DATA_MATRIX = "datamatrix", "Data Matrix"
        PDF417 = "pdf417", "PDF417"
        AZTEC = "aztec", "Aztec"

    class PassType(models.TextChoices):
        LOYALTY_CARD = "loyalty_card", "Loyalty card"
        VOUCHER = "voucher", "Voucher"
        COUPON = "coupon", "Coupon"
        TICKET = "ticket", "Ticket"
        BOARDING_PASS = "boarding_pass", "Boarding pass"

    class ColorMode(models.TextChoices):
        CUSTOM = "custom", "Custom"
        AUTO = "auto", "Auto from icon"

    class ArchiveReason(models.TextChoices):
        MANUAL = "manual", "Manual"
        USED = "used", "Used/redeemed"
        EVENT_ENDED = "event_ended", "Event ended"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="loyalty_cards")
    name = models.CharField(max_length=120)
    logo = models.CharField(max_length=120, blank=True)
    icon_key = models.CharField(max_length=48, blank=True, default="")
    color = models.CharField(max_length=24, default="#6750A4")
    color_mode = models.CharField(max_length=12, choices=ColorMode.choices, default=ColorMode.CUSTOM)
    pass_type = models.CharField(max_length=24, choices=PassType.choices, default=PassType.LOYALTY_CARD)
    holder_name = models.CharField(max_length=120, blank=True)
    holder_membership = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="held_loyalty_cards",
    )
    customer_number = models.CharField(max_length=160, blank=True)
    barcode_value = models.TextField()
    barcode_format = models.CharField(max_length=24, choices=BarcodeFormat.choices, default=BarcodeFormat.CODE128)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_loyalty_cards",
    )
    shared_with = models.ManyToManyField(Membership, blank=True, related_name="shared_loyalty_cards")
    favorite = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archive_reason = models.CharField(max_length=24, choices=ArchiveReason.choices, blank=True, default="")
    used_at = models.DateTimeField(null=True, blank=True)
    restore_until = models.DateTimeField(null=True, blank=True)
    undo_window_minutes = models.PositiveSmallIntegerField(default=10)
    event_ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-favorite", "sort_order", "name"]


# Public domain vocabulary for new code while preserving the historical model/table name.
PassItem = LoyaltyCard


class NotificationBatch(TimestampedModel):
    """Bounded, durable outbox; one independent stream per member and resource."""
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="notification_batches")
    bucket = models.CharField(max_length=180)
    events = models.JSONField(default=dict)
    due_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "bucket"], name="notification_member_bucket_unique")]


class NotificationBadgeState(TimestampedModel):
    """Account-wide unread activity count mirrored to supported PWA launchers."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="familyos_badge_state")
    unread_count = models.PositiveIntegerField(default=0)
