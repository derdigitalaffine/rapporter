import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0005_expense_ledgers"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpenseBudget",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "period_type",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("month", "Month"),
                            ("year", "Year"),
                            ("date_range", "Date range"),
                            ("context", "Context"),
                        ],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("starts_on", models.DateField(blank=True, null=True)),
                ("ends_on", models.DateField(blank=True, null=True)),
                ("archived", models.BooleanField(default=False)),
                (
                    "family",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="expense_budgets",
                        to="family.family",
                    ),
                ),
                (
                    "ledger",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="budgets",
                        to="expenses.expenseledger",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="expenses.expensebudget",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
                "indexes": [
                    models.Index(fields=["family", "ledger", "archived"], name="exp_budget_ledger_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("amount__gte", 0)),
                        name="expense_budget_amount_nonneg",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ExpenseBudgetAllocation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("amount_in_budget_currency", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "budget",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="allocations",
                        to="expenses.expensebudget",
                    ),
                ),
                (
                    "expense",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="budget_allocations",
                        to="expenses.expense",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("expense", "budget"),
                        name="expense_budget_allocation_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("amount_in_budget_currency__gt", 0)),
                        name="expense_budget_allocation_positive",
                    ),
                ],
            },
        ),
    ]
