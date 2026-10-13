from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0009_expense_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="expenseledger",
            name="default_participants",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="expenseledger",
            name="default_split_type",
            field=models.CharField(
                choices=[("equal", "Equal"), ("percentage", "Percentage"), ("shares", "Shares")],
                default="equal",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="expenseledger",
            name="default_split_values",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
