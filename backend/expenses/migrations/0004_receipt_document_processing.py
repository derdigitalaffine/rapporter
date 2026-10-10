from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0002_document_processing"),
        ("expenses", "0003_expense_client_request_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="receipt_document",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="receipt_expense",
                to="documents.document",
            ),
        ),
        migrations.AddField(
            model_name="receiptextraction",
            name="processing_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="receipt_extractions",
                to="documents.documentprocessingrun",
            ),
        ),
    ]
