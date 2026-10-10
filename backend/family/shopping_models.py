from django.conf import settings
from django.db import models

from .models import Family, ShoppingList, TimestampedModel


class ShoppingStore(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="shopping_stores")
    name = models.CharField(max_length=120)
    branch_label = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=240, blank=True)
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
