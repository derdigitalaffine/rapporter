from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "expenses"

    def ready(self):
        from documents.consumers import register_processing_consumer
        from .document_receipts import consume_receipt_processing_run

        register_processing_consumer("expense", "receipt", consume_receipt_processing_run)
