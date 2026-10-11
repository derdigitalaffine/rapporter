from django.conf import settings
from django.db import models

from family.models import Family, Membership, TimestampedModel


class Wishlist(TimestampedModel):
    class Visibility(models.TextChoices):
        SELECTED = "selected", "Selected"
        FAMILY = "family", "Family"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="wishlists")
    owner_membership = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="owned_wishlists")
    title = models.CharField(max_length=160)
    visibility = models.CharField(max_length=16, choices=Visibility.choices, default=Visibility.SELECTED, db_index=True)
    active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wishlists_created",
    )

    class Meta:
        ordering = ["-updated_at", "title"]
        indexes = [
            models.Index(fields=["family", "active", "visibility"], name="wishlist_family_vis_idx"),
            models.Index(fields=["owner_membership", "active"], name="wishlist_owner_active_idx"),
        ]


class WishlistAccess(TimestampedModel):
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="access_entries")
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="wishlist_access_entries")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["wishlist", "membership"], name="wishlist_access_member_uniq"),
        ]


class WishlistItem(TimestampedModel):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="items")
    title = models.CharField(max_length=180)
    url = models.URLField(max_length=1000, blank=True)
    note = models.TextField(blank=True)
    priority = models.CharField(max_length=12, choices=Priority.choices, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wishlist_items_created",
    )
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["wishlist", "archived_at"], name="wishlist_item_active_idx")]


class WishlistReservation(TimestampedModel):
    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        PURCHASED = "purchased", "Purchased"

    item = models.OneToOneField(WishlistItem, on_delete=models.CASCADE, related_name="reservation")
    reserved_by = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name="wishlist_reservations")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RESERVED, db_index=True)
    note = models.CharField(max_length=240, blank=True)

    class Meta:
        indexes = [models.Index(fields=["reserved_by", "status"], name="wishlist_reserver_idx")]
