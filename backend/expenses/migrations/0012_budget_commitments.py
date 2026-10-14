import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("expenses", "0011_budget_planning_estimates"),
    ]

    operations = [
        migrations.CreateModel(
            name="BudgetCommitment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_type", models.CharField(max_length=32)),
                ("source_id", models.UUIDField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(max_length=3)),
                ("status", models.CharField(choices=[("active", "Active"), ("consumed", "Consumed"), ("released", "Released")], db_index=True, default="active", max_length=16)),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("budget", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="commitments", to="expenses.expensebudget")),
                ("consumed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="consumed_budget_commitments", to="expenses.expense")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="budget_commitments_created", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budget_commitments", to="family.family")),
                ("ledger", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="budget_commitments", to="expenses.expenseledger")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="budgetcommitment",
            index=models.Index(fields=["family", "ledger", "status"], name="exp_commit_ledger_idx"),
        ),
        migrations.AddIndex(
            model_name="budgetcommitment",
            index=models.Index(fields=["family", "source_type", "source_id"], name="exp_commit_source_idx"),
        ),
        migrations.AddConstraint(
            model_name="budgetcommitment",
            constraint=models.CheckConstraint(condition=models.Q(amount__gt=0), name="expense_commit_amount_positive"),
        ),
        migrations.AddConstraint(
            model_name="budgetcommitment",
            constraint=models.UniqueConstraint(condition=models.Q(status="active"), fields=("family", "source_type", "source_id"), name="expense_commit_active_source_unique"),
        ),
    ]
