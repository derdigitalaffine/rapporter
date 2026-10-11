from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0006_expense_budgets"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="funding_source",
            field=models.CharField(
                choices=[("member", "Member"), ("shared", "Shared")],
                default="member",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="expense",
            name="paid_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="expenses_paid",
                to="family.membership",
            ),
        ),
        migrations.AddConstraint(
            model_name="expense",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("funding_source", "member"), ("paid_by__isnull", False))
                    | models.Q(("funding_source", "shared"), ("paid_by__isnull", True))
                ),
                name="expense_funding_source_consistent",
            ),
        ),
    ]
