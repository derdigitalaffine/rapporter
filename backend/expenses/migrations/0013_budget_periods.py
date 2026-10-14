from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0012_budget_commitments"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpenseBudgetPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period_type", models.CharField(choices=[("open", "Open"), ("month", "Month"), ("year", "Year"), ("date_range", "Date range"), ("context", "Context")], max_length=16)),
                ("starts_on", models.DateField()),
                ("ends_on", models.DateField()),
                ("planned_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("carryover_amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("rollover_policy", models.CharField(choices=[("reset", "Reset"), ("carry_positive", "Carry positive remainder")], default="reset", max_length=24)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("budget", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="periods", to="expenses.expensebudget")),
            ],
            options={
                "ordering": ["-starts_on", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="expensebudgetperiod",
            index=models.Index(fields=["budget", "starts_on", "ends_on"], name="exp_budget_period_idx"),
        ),
        migrations.AddConstraint(
            model_name="expensebudgetperiod",
            constraint=models.UniqueConstraint(fields=("budget", "period_type", "starts_on", "ends_on"), name="expense_budget_period_unique"),
        ),
        migrations.AddConstraint(
            model_name="expensebudgetperiod",
            constraint=models.CheckConstraint(condition=models.Q(("planned_amount__gte", 0)), name="expense_budget_period_plan_nonneg"),
        ),
        migrations.AddConstraint(
            model_name="expensebudgetperiod",
            constraint=models.CheckConstraint(condition=models.Q(("carryover_amount__gte", 0)), name="expense_budget_period_carry_nonneg"),
        ),
    ]
