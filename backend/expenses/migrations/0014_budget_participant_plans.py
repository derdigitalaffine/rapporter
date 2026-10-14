import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0013_budget_periods"),
        ("family", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpenseBudgetParticipantPlan",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("spending_limit", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("planned_share", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("budget", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="participant_plans", to="expenses.expensebudget")),
                ("ledger", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participant_plans", to="expenses.expenseledger")),
                ("member", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="expense_budget_plans", to="family.membership")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="expensebudgetparticipantplan",
            constraint=models.UniqueConstraint(condition=models.Q(budget__isnull=False), fields=("budget", "member"), name="expense_budget_participant_unique"),
        ),
        migrations.AddConstraint(
            model_name="expensebudgetparticipantplan",
            constraint=models.UniqueConstraint(condition=models.Q(budget__isnull=True), fields=("ledger", "member"), name="expense_ledger_participant_unique"),
        ),
        migrations.AddConstraint(
            model_name="expensebudgetparticipantplan",
            constraint=models.CheckConstraint(condition=models.Q(spending_limit__isnull=True) | models.Q(spending_limit__gte=0), name="expense_budget_limit_nonneg"),
        ),
        migrations.AddConstraint(
            model_name="expensebudgetparticipantplan",
            constraint=models.CheckConstraint(condition=models.Q(planned_share__isnull=True) | models.Q(planned_share__gte=0), name="expense_budget_share_plan_nonneg"),
        ),
        migrations.AddConstraint(
            model_name="expensebudgetparticipantplan",
            constraint=models.CheckConstraint(condition=models.Q(spending_limit__isnull=False) | models.Q(planned_share__isnull=False), name="expense_budget_participant_has_value"),
        ),
    ]
