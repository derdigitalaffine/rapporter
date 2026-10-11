from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0007_expense_funding_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="original_amount",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="expense",
            name="original_currency",
            field=models.CharField(blank=True, max_length=3, null=True),
        ),
        migrations.AddField(
            model_name="expense",
            name="fx_rate",
            field=models.DecimalField(blank=True, decimal_places=10, max_digits=20, null=True),
        ),
        migrations.AddConstraint(
            model_name="expense",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("fx_rate__isnull", True),
                        ("original_amount__isnull", True),
                        ("original_currency__isnull", True),
                    )
                    | models.Q(
                        ("fx_rate__isnull", False),
                        ("original_amount__isnull", False),
                        ("original_currency__isnull", False),
                    )
                ),
                name="expense_fx_all_or_none",
            ),
        ),
        migrations.AddConstraint(
            model_name="expense",
            constraint=models.CheckConstraint(
                condition=models.Q(("original_amount__isnull", True), ("original_amount__gt", 0), _connector="OR"),
                name="expense_fx_original_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="expense",
            constraint=models.CheckConstraint(
                condition=models.Q(("fx_rate__isnull", True), ("fx_rate__gt", 0), _connector="OR"),
                name="expense_fx_rate_positive",
            ),
        ),
    ]
