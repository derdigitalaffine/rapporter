import uuid

from django.db import migrations, models
import django.db.models.deletion


DEFAULT_LEDGER_NAME = "Familie – laufend"


def backfill_default_ledgers(apps, schema_editor):
    Family = apps.get_model("family", "Family")
    ExpenseLedger = apps.get_model("expenses", "ExpenseLedger")
    Expense = apps.get_model("expenses", "Expense")
    Settlement = apps.get_model("expenses", "Settlement")

    for family_id in Family.objects.values_list("id", flat=True).iterator():
        ledger, _ = ExpenseLedger.objects.get_or_create(
            family_id=family_id,
            is_default=True,
            defaults={"name": DEFAULT_LEDGER_NAME, "base_currency": "EUR"},
        )
        Expense.objects.filter(family_id=family_id, ledger__isnull=True).update(ledger_id=ledger.id)
        Settlement.objects.filter(family_id=family_id, ledger__isnull=True).update(ledger_id=ledger.id)


def unassign_default_ledgers(apps, schema_editor):
    ExpenseLedger = apps.get_model("expenses", "ExpenseLedger")
    Expense = apps.get_model("expenses", "Expense")
    Settlement = apps.get_model("expenses", "Settlement")

    Expense.objects.update(ledger=None)
    Settlement.objects.update(ledger=None)
    ExpenseLedger.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0004_receipt_document_processing_run"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpenseLedger",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("base_currency", models.CharField(default="EUR", max_length=3)),
                ("budget_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("is_default", models.BooleanField(default=False)),
                ("archived", models.BooleanField(default=False)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="expense_ledgers", to="family.family")),
            ],
            options={
                "ordering": ["-is_default", "created_at"],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("family",), name="expense_one_default_ledger"),
                    models.CheckConstraint(condition=models.Q(("budget_amount__isnull", True), ("budget_amount__gte", 0), _connector="OR"), name="expense_ledger_budget_nonneg"),
                ],
            },
        ),
        migrations.AddField(
            model_name="expense",
            name="ledger",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="expenses", to="expenses.expenseledger"),
        ),
        migrations.AddField(
            model_name="settlement",
            name="ledger",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="settlements", to="expenses.expenseledger"),
        ),
        migrations.RunPython(backfill_default_ledgers, unassign_default_ledgers),
    ]
