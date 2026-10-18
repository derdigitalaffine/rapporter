from django.conf import settings
from django.db import models

from .models import Family, ShoppingItem, ShoppingList, TimestampedModel


class MealTag(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="meal_tags")
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["family", "name"], name="uniq_meal_tag_family_name"),
        ]

    def __str__(self):
        return self.name


class MealDish(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="meal_dishes")
    name = models.CharField(max_length=160)
    default_servings = models.PositiveSmallIntegerField(default=2)
    favorite = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    tags = models.ManyToManyField(MealTag, blank=True, related_name="dishes")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_meal_dishes",
    )

    class Meta:
        ordering = ["-favorite", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["family", "name"], name="uniq_meal_dish_family_name"),
        ]

    def __str__(self):
        return self.name


class MealIngredient(TimestampedModel):
    dish = models.ForeignKey(MealDish, on_delete=models.CASCADE, related_name="ingredients")
    name = models.CharField(max_length=160)
    quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    normally_on_hand = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at", "id"]


class MealPlanEntry(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="meal_plan_entries")
    date = models.DateField(db_index=True)
    slot = models.CharField(max_length=80)
    dish = models.ForeignKey(
        MealDish,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plan_entries",
    )
    title = models.CharField(max_length=160, blank=True)
    servings = models.PositiveSmallIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)
    tags = models.ManyToManyField(MealTag, blank=True, related_name="plan_entries")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_meal_plan_entries",
    )

    class Meta:
        ordering = ["date", "slot", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["family", "date", "slot"], name="uniq_meal_plan_family_date_slot"),
        ]

    @property
    def display_title(self):
        return self.dish.name if self.dish_id else self.title


class MealPlanDayTag(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="meal_plan_day_tags")
    date = models.DateField(db_index=True)
    tag = models.ForeignKey(MealTag, on_delete=models.CASCADE, related_name="day_assignments")

    class Meta:
        ordering = ["date", "tag__name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["family", "date", "tag"], name="uniq_meal_day_tag"),
        ]


class MealPlanTemplate(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="meal_plan_templates")
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_meal_plan_templates",
    )

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["family", "name"], name="uniq_meal_template_family_name"),
        ]


class MealPlanTemplateEntry(TimestampedModel):
    template = models.ForeignKey(MealPlanTemplate, on_delete=models.CASCADE, related_name="entries")
    weekday = models.PositiveSmallIntegerField()
    slot = models.CharField(max_length=80)
    dish = models.ForeignKey(
        MealDish,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_entries",
    )
    title = models.CharField(max_length=160, blank=True)
    servings = models.PositiveSmallIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)
    tags = models.ManyToManyField(MealTag, blank=True, related_name="template_entries")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["weekday", "position", "slot", "id"]
        constraints = [
            models.UniqueConstraint(fields=["template", "weekday", "slot"], name="uniq_meal_template_day_slot"),
        ]


class MealPlanTemplateDayTag(TimestampedModel):
    template = models.ForeignKey(MealPlanTemplate, on_delete=models.CASCADE, related_name="day_tags")
    weekday = models.PositiveSmallIntegerField()
    tag = models.ForeignKey(MealTag, on_delete=models.CASCADE, related_name="template_day_assignments")

    class Meta:
        ordering = ["weekday", "tag__name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["template", "weekday", "tag"], name="uniq_meal_template_day_tag"),
        ]


class MealShoppingTransfer(TimestampedModel):
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="meal_shopping_transfers")
    start_date = models.DateField()
    end_date = models.DateField()
    shopping_list = models.ForeignKey(
        ShoppingList,
        on_delete=models.CASCADE,
        related_name="meal_plan_transfers",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_meal_shopping_transfers",
    )

    class Meta:
        ordering = ["-start_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["family", "start_date", "end_date", "shopping_list"],
                name="uniq_meal_transfer_range_list",
            ),
        ]


class MealShoppingTransferItem(TimestampedModel):
    transfer = models.ForeignKey(MealShoppingTransfer, on_delete=models.CASCADE, related_name="items")
    demand_key = models.CharField(max_length=255)
    shopping_item = models.ForeignKey(
        ShoppingItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="meal_plan_transfer_items",
    )
    generated_name = models.CharField(max_length=160)
    generated_quantity = models.CharField(max_length=40, blank=True)
    shopping_item_version = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["transfer", "demand_key"], name="uniq_meal_transfer_demand"),
        ]
