from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("expenses", "0010_expenseledger_split_defaults")]

    operations = [
        migrations.AddField(
            model_name="expenseledger", name="estimated_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="expensebudget", name="estimated_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="expensebudget", name="client_request_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="expenseledger",
            constraint=models.CheckConstraint(
                condition=models.Q(estimated_amount__isnull=True) | models.Q(estimated_amount__gte=0),
                name="expense_ledger_estimate_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="expensebudget",
            constraint=models.CheckConstraint(
                condition=models.Q(estimated_amount__isnull=True) | models.Q(estimated_amount__gte=0),
                name="expense_budget_estimate_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="expensebudget",
            constraint=models.UniqueConstraint(
                fields=("ledger", "client_request_id"),
                condition=models.Q(client_request_id__isnull=False),
                name="expense_budget_request_unique",
            ),
        ),
    ]
