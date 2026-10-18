import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0252_shopping_purchase_store_context"),
    ]

    operations = [
        migrations.CreateModel(
            name="MealTag",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meal_tags", to="family.family")),
            ],
            options={
                "ordering": ["name", "id"],
                "constraints": [models.UniqueConstraint(fields=("family", "name"), name="uniq_meal_tag_family_name")],
            },
        ),
        migrations.CreateModel(
            name="MealDish",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("default_servings", models.PositiveSmallIntegerField(default=2)),
                ("favorite", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_meal_dishes", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meal_dishes", to="family.family")),
                ("tags", models.ManyToManyField(blank=True, related_name="dishes", to="family.mealtag")),
            ],
            options={
                "ordering": ["-favorite", "name", "id"],
                "constraints": [models.UniqueConstraint(fields=("family", "name"), name="uniq_meal_dish_family_name")],
            },
        ),
        migrations.CreateModel(
            name="MealIngredient",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("quantity", models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ("unit", models.CharField(blank=True, max_length=32)),
                ("normally_on_hand", models.BooleanField(default=False)),
                ("position", models.PositiveIntegerField(default=0)),
                ("dish", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ingredients", to="family.mealdish")),
            ],
            options={"ordering": ["position", "created_at", "id"]},
        ),
        migrations.CreateModel(
            name="MealPlanEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField(db_index=True)),
                ("slot", models.CharField(max_length=80)),
                ("title", models.CharField(blank=True, max_length=160)),
                ("servings", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_meal_plan_entries", to=settings.AUTH_USER_MODEL)),
                ("dish", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="plan_entries", to="family.mealdish")),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meal_plan_entries", to="family.family")),
                ("tags", models.ManyToManyField(blank=True, related_name="plan_entries", to="family.mealtag")),
            ],
            options={
                "ordering": ["date", "slot", "created_at", "id"],
                "constraints": [models.UniqueConstraint(fields=("family", "date", "slot"), name="uniq_meal_plan_family_date_slot")],
            },
        ),
        migrations.CreateModel(
            name="MealPlanDayTag",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField(db_index=True)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meal_plan_day_tags", to="family.family")),
                ("tag", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="day_assignments", to="family.mealtag")),
            ],
            options={
                "ordering": ["date", "tag__name", "id"],
                "constraints": [models.UniqueConstraint(fields=("family", "date", "tag"), name="uniq_meal_day_tag")],
            },
        ),
        migrations.CreateModel(
            name="MealPlanTemplate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_meal_plan_templates", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meal_plan_templates", to="family.family")),
            ],
            options={
                "ordering": ["name", "id"],
                "constraints": [models.UniqueConstraint(fields=("family", "name"), name="uniq_meal_template_family_name")],
            },
        ),
        migrations.CreateModel(
            name="MealPlanTemplateEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("weekday", models.PositiveSmallIntegerField()),
                ("slot", models.CharField(max_length=80)),
                ("title", models.CharField(blank=True, max_length=160)),
                ("servings", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("position", models.PositiveIntegerField(default=0)),
                ("dish", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="template_entries", to="family.mealdish")),
                ("tags", models.ManyToManyField(blank=True, related_name="template_entries", to="family.mealtag")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="family.mealplantemplate")),
            ],
            options={
                "ordering": ["weekday", "position", "slot", "id"],
                "constraints": [models.UniqueConstraint(fields=("template", "weekday", "slot"), name="uniq_meal_template_day_slot")],
            },
        ),
        migrations.CreateModel(
            name="MealPlanTemplateDayTag",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("weekday", models.PositiveSmallIntegerField()),
                ("tag", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="template_day_assignments", to="family.mealtag")),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="day_tags", to="family.mealplantemplate")),
            ],
            options={
                "ordering": ["weekday", "tag__name", "id"],
                "constraints": [models.UniqueConstraint(fields=("template", "weekday", "tag"), name="uniq_meal_template_day_tag")],
            },
        ),
        migrations.CreateModel(
            name="MealShoppingTransfer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_meal_shopping_transfers", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meal_shopping_transfers", to="family.family")),
                ("shopping_list", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="meal_plan_transfers", to="family.shoppinglist")),
            ],
            options={
                "ordering": ["-start_date", "-created_at"],
                "constraints": [models.UniqueConstraint(fields=("family", "start_date", "end_date", "shopping_list"), name="uniq_meal_transfer_range_list")],
            },
        ),
        migrations.CreateModel(
            name="MealShoppingTransferItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("demand_key", models.CharField(max_length=255)),
                ("generated_name", models.CharField(max_length=160)),
                ("generated_quantity", models.CharField(blank=True, max_length=40)),
                ("shopping_item_version", models.PositiveBigIntegerField(default=0)),
                ("shopping_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="meal_plan_transfer_items", to="family.shoppingitem")),
                ("transfer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="family.mealshoppingtransfer")),
            ],
            options={
                "ordering": ["created_at", "id"],
                "constraints": [models.UniqueConstraint(fields=("transfer", "demand_key"), name="uniq_meal_transfer_demand")],
            },
        ),
    ]
