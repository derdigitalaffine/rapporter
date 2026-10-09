from django.conf import settings
from django.db import models

from .models import Family, Membership, TimestampedModel


class NotificationPreference(TimestampedModel):
    membership = models.OneToOneField(Membership, on_delete=models.CASCADE, related_name="notification_preference")
    tasks = models.BooleanField(default=True)
    task_assigned = models.BooleanField(default=True)
    shopping = models.BooleanField(default=True)
    calendar = models.BooleanField(default=True)
    family_updates = models.BooleanField(default=True)
    messages = models.BooleanField(default=True)
    routines = models.BooleanField(default=True)


class LoyaltyCard(TimestampedModel):
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

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="loyalty_cards")
    name = models.CharField(max_length=120)
    logo = models.CharField(max_length=120, blank=True)
    color = models.CharField(max_length=24, default="#6750A4")
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

    class Meta:
        ordering = ["-favorite", "sort_order", "name"]
