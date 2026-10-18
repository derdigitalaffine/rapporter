from django.conf import settings
from django.db import models
from django.utils import timezone

from .models import Family, Membership, ShoppingList, TimestampedModel


class ShoppingStore(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="shopping_stores")
    name = models.CharField(max_length=120)
    branch_label = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=240, blank=True)
    location_provider = models.CharField(max_length=32, blank=True)
    location_ref = models.CharField(max_length=160, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    website_url = models.URLField(max_length=500, blank=True)
    offers_url = models.URLField(max_length=500, blank=True)
    note = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_shopping_stores",
    )

    @property
    def display_label(self):
        return f"{self.name} · {self.branch_label}" if self.branch_label else self.name

    class Meta:
        ordering = ["sort_order", "name", "branch_label", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "location_provider", "location_ref"],
                condition=models.Q(location_provider__gt="", location_ref__gt=""),
                name="shop_store_location_ref_uniq",
            ),
        ]
        indexes = [models.Index(fields=["family", "active", "sort_order"], name="shop_store_family_idx")]


class ShoppingListStoreProfile(TimestampedModel):
    shopping_list = models.OneToOneField(
        ShoppingList,
        on_delete=models.CASCADE,
        related_name="store_profile_assignment",
    )
    store = models.ForeignKey(
        ShoppingStore,
        on_delete=models.CASCADE,
        related_name="list_assignments",
    )

    class Meta:
        ordering = ["created_at"]


class ShoppingListAccess(TimestampedModel):
    """Object-level shopping visibility and responsibility.

    Absence of this row intentionally means the legacy family-wide contract.
    Responsibility is descriptive only and never grants access.
    """

    class Visibility(models.TextChoices):
        FAMILY = "family", "Whole family"
        PRIVATE = "private", "Private"
        SELECTED = "selected", "Selected people"

    shopping_list = models.OneToOneField(
        ShoppingList,
        on_delete=models.CASCADE,
        related_name="access_settings",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_shopping_list_access",
    )
    visibility = models.CharField(
        max_length=16,
        choices=Visibility.choices,
        default=Visibility.FAMILY,
        db_index=True,
    )
    visible_members = models.ManyToManyField(
        Membership,
        blank=True,
        related_name="visible_shopping_lists",
    )
    responsible_members = models.ManyToManyField(
        Membership,
        blank=True,
        related_name="responsible_shopping_lists",
    )


class ShoppingSession(TimestampedModel):
    """One concrete collaborative in-store execution of a ShoppingList."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="shopping_sessions")
    shopping_list = models.ForeignKey(ShoppingList, on_delete=models.CASCADE, related_name="shopping_sessions")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="started_shopping_sessions",
    )
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_shopping_sessions",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    activity_seq = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["shopping_list"],
                condition=models.Q(status="active"),
                name="shop_one_active_session",
            )
        ]
        indexes = [
            models.Index(fields=["family", "status", "last_activity_at"], name="shop_session_family_idx"),
        ]


class ShoppingSessionParticipant(TimestampedModel):
    session = models.ForeignKey(ShoppingSession, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shopping_session_participations",
    )
    joined_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "user"], name="shop_session_participant_uniq"),
        ]
        ordering = ["joined_at"]


class ShoppingSessionActivity(TimestampedModel):
    class Kind(models.TextChoices):
        ITEM_ADDED = "item_added", "Item added"
        ITEM_CHECKED = "item_checked", "Item checked"
        ITEM_REOPENED = "item_reopened", "Item reopened"

    session = models.ForeignKey(ShoppingSession, on_delete=models.CASCADE, related_name="activities")
    sequence = models.PositiveBigIntegerField()
    kind = models.CharField(max_length=24, choices=Kind.choices)
    item_id = models.UUIDField(null=True, blank=True)
    item_name = models.CharField(max_length=160, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shopping_session_activities",
    )
    # Learning uses only this client-local ordering. ``sequence`` remains the
    # server cursor for collaboration and is deliberately never a learning clock.
    client_stream = models.CharField(max_length=128, blank=True, default="")
    client_sequence = models.PositiveBigIntegerField(null=True, blank=True)
    mutation_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["session", "sequence"], name="shop_session_activity_seq_uniq"),
            models.UniqueConstraint(
                fields=["session", "client_stream", "client_sequence"],
                condition=models.Q(client_stream__gt="", client_sequence__isnull=False),
                name="shop_activity_client_seq_uniq",
            ),
            models.UniqueConstraint(
                fields=["session", "mutation_id"],
                condition=models.Q(mutation_id__isnull=False),
                name="shop_activity_mutation_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["session", "sequence"], name="shop_session_cursor_idx"),
            models.Index(fields=["session", "client_stream", "client_sequence"], name="shop_activity_client_idx"),
        ]


class ShoppingTemplate(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="shopping_templates")
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=500, blank=True)
    default_store = models.ForeignKey(
        ShoppingStore,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shopping_templates",
    )
    archived = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_shopping_templates",
    )

    class Meta:
        ordering = ["archived", "sort_order", "name", "created_at"]
        indexes = [models.Index(fields=["family", "archived", "sort_order"], name="shop_tpl_family_idx")]


class ShoppingTemplateItem(TimestampedModel):
    template = models.ForeignKey(ShoppingTemplate, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=160)
    normalized_name = models.CharField(max_length=160, editable=False)
    quantity = models.CharField(max_length=40, blank=True)
    category = models.CharField(max_length=80, blank=True)
    aisle = models.CharField(max_length=80, blank=True)
    note = models.CharField(max_length=240, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "normalized_name"],
                name="uniq_shopping_template_item_name",
            )
        ]
